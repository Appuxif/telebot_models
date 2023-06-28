from typing import Any, Callable, ClassVar, Coroutine, Generic, Optional, Type, TypeVar

from bson import ObjectId
from motor import core
from pydantic import BaseModel, Field, PrivateAttr
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult
from typing_extensions import Self


class PyObjectId(ObjectId):
    """ObjectID to use with pydantic models"""

    @classmethod
    def __get_validators__(cls) -> Callable:
        yield cls.validate

    @classmethod
    def validate(cls, value: str) -> ObjectId:
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid objectid")
        return ObjectId(value)

    @classmethod
    def __modify_schema__(cls, field_schema: Any) -> None:
        field_schema.update(type="string")


class AllowPopulationByFieldName(BaseModel):
    """Allow Population By Field Name"""

    class Config:
        """Config"""

        allow_population_by_field_name = True


class ModelConfig:
    """Model Config"""

    class Config(AllowPopulationByFieldName.Config):
        """The base model config"""

        use_enum_values = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class Model(ModelConfig, BaseModel):
    """The base model"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias='_id')
    manager: ClassVar[Type['BaseModelManager']]

    class _CustomCache:
        """Cache"""

    __custom_cache__: _CustomCache = PrivateAttr(default_factory=_CustomCache)

    async def update(self, **kwargs) -> None:
        await self.manager.update(self, **kwargs)

    async def insert(self, **kwargs) -> None:
        await self.manager.insert(self, **kwargs)

    async def delete(self) -> None:
        await self.manager.delete(self)


T = TypeVar('T', bound=Model)


class ModelManagerMeta(type):
    """Model Manager Meta"""

    def __new__(mcs, name, bases, dct):  # noqa
        # pylint: disable=bad-mcs-classmethod-argument
        manager = super().__new__(mcs, name, bases, dct)
        manager.model.manager = manager  # noqa
        return manager


class BaseModelManager(Generic[T], metaclass=ModelManagerMeta):
    """Model Manager"""

    model: Type[T] = Model
    collection: str = ''
    _relation_map: list[tuple[type, str, str]] = []

    def __init__(self, document_filter: dict | None = None):
        self.document_filter: dict = document_filter or {}

    @classmethod
    def relation_map(cls, field_name, model_field_name):
        def decorator(model_cls: Type[T]) -> Type[T]:
            cls._relation_map.append((model_cls, field_name, model_field_name))
            rel_obj_name = cls.__name__.replace('ModelManager', '').lower()

            def related_model_set(self):
                return model_cls.manager({field_name: getattr(self, model_field_name)})

            def by_related_obj(self, obj_id: PyObjectId | list[PyObjectId]):
                if isinstance(obj_id, list):
                    return self.filter({field_name: {'$in': obj_id}})
                return self.filter({field_name: obj_id})

            async def obj(self: Model):
                __cached_key__ = '__cached_' + rel_obj_name + '__'
                if getattr(self.__custom_cache__, __cached_key__, None) is None:
                    setattr(self.__custom_cache__, __cached_key__, await cls().find_one(getattr(self, field_name)))
                return getattr(self.__custom_cache__, __cached_key__)

            setattr(cls.model, model_cls.__name__.lower() + '_set', related_model_set)
            setattr(model_cls.manager, 'by_' + rel_obj_name, by_related_obj)
            setattr(model_cls, rel_obj_name, obj)
            return model_cls

        return decorator

    @classmethod
    def get_collection(cls) -> core.AgnosticCollection:
        return await CollectionGetter.get_collection(cls.collection)

    @classmethod
    async def insert(cls, model: T, **kwargs) -> InsertOneResult:
        include: set | None = kwargs.get('include')
        exclude: set | None = kwargs.get('exclude')

        if include:
            exclude = None
        else:
            exclude = exclude or set()
            exclude.add('id')

        document = model.dict(by_alias=True, exclude=exclude, include=include)
        result = await cls.get_collection().insert_one(document)
        model.id = document['_id']
        return result

    @classmethod
    async def update(cls, model: T, **kwargs) -> UpdateResult:
        include: set | None = kwargs.get('include')
        exclude: set | None = kwargs.get('exclude')

        if include:
            exclude = None
        else:
            exclude = exclude or set()
            exclude.add('id')

        return await cls.get_collection().update_one(
            {'_id': model.id}, {'$set': model.dict(by_alias=True, exclude=exclude, include=include)}
        )

    async def update_many(self, *args, **kwargs) -> UpdateResult:
        return await self.get_collection().update_many(self.document_filter, *args, **kwargs)

    @classmethod
    async def delete(cls, model: T) -> DeleteResult:
        _cls: Type[Model]
        for _cls, field_name, model_field_name in cls._relation_map:
            objs = await _cls.manager({field_name: getattr(model, model_field_name)}).find_all()
            for obj in objs:
                await obj.delete()
        return await cls.get_collection().delete_one({'_id': model.id})

    async def delete_many(self, *args, **kwargs) -> DeleteResult:
        return await self.get_collection().delete_many(self.document_filter, *args, **kwargs)

    def filter(self, document_filter: dict | None = None) -> Self:
        document_filter = document_filter or {}
        return self.__class__({**self.document_filter, **document_filter})

    async def find_all(self, *args, **kwargs) -> list[T]:
        return [
            self.model.parse_obj(obj)
            for obj in await self.get_collection().find(self.document_filter, *args, **kwargs).to_list(None)
        ]

    async def find_one(self, *args, raise_exception=True, **kwargs) -> Optional[T]:
        if args and isinstance(args[0], ObjectId):
            self.document_filter.update({'_id': args[0]})
            args = args[1:]
        document = await self.get_collection().find_one(self.document_filter, *args, **kwargs)
        if document is None and raise_exception:
            raise ValueError(f'Document not found by filter {self.document_filter}')
        if document is None:
            return None
        return self.model.parse_obj(document)

    async def count(self) -> int:
        return await self.get_collection().count_documents(self.document_filter)


class CollectionGetter:
    @staticmethod
    async def get_collection(collection: str) -> core.AgnosticCollection:
        raise NotImplementedError(f'Not implemented for {collection}')


def set_collection_getter(func: Callable[[str], Coroutine[Any, Any, core.AgnosticCollection]]) -> None:
    CollectionGetter.get_collection = func
