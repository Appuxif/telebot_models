import setuptools

with open('README.md', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

setuptools.setup(
    name='telebot_models',
    version='0.0.7b2',
    author='Appuxif',
    author_email='app@mail.com',
    description='A Python package with utils for telebot models based on mongo-motor',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/Appuxif/telebot_models',
    project_urls={
        'Bug Tracker': 'https://github.com/Appuxif/telebot_models/issues',
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    package_dir={'': '.'},
    packages=['telebot_models'],
    package_data={},
    python_requires='>=3.8',
    install_requires=[
        "pymongo>=4.3.3,<5.0.0",
        "motor>=3.1.2,<4.0.0",
        "pydantic>=1.10.9,<1.20.0",
    ],
)
