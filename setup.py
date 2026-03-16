from setuptools import find_packages, setup

package_name = 'elsabot_audio_output'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Scott Horton',
    maintainer_email='none@none.com',
    description='Audio output processor for Elsabot robot',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'elsabot_audio_output = elsabot_audio_output.servers:main',
        ],
    },
)
