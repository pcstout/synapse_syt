import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="syt",
    version="0.0.beta1",
    author="Patrick Stout",
    author_email="pstout@prevagroup.com",
    description="Synapse check in/out utility.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pcstout/synapse_syt",
    packages=setuptools.find_packages(exclude=['docs', 'tests*']),
    classifiers=(
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ),
    entry_points={
        'console_scripts': [
            "syt = syt.syt:main"
        ]
    }
)
