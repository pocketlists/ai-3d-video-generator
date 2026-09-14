from setuptools import setup, find_packages

setup(
    name="ai-3d-video-generator",
    version="1.0.0",
    description="AI-powered automated 3D video generation system via GitHub Actions",
    author="pocketlists",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "PyYAML>=6.0",
        "psutil>=5.9",
        "Pillow>=10.0",
        "requests>=2.31",
    ],
    extras_require={
        "tts": ["gtts>=2.4"],
        "dev": ["pytest>=7.4", "pytest-cov>=4.1"],
    },
    entry_points={
        "console_scripts": [
            "pipeline=controller.orchestrator:main",
        ],
    },
)
