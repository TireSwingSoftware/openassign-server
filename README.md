# OpenAssign-Server

openassign-server is an open source project written in Python which provides a
fully equipped course management system.  It is actively developed
by TireSwingSoftware.

# Developer Guide

The following guide may serve as a starting point for developers unfamiliar
with the project installation steps or for the required packages.

## Getting set up

The install process on a developer workstation for openassign-server
is pretty straight forward. The steps are outlined in detail below
for specific operating systems.

Several components including system libraries and other dependencies
are required for the python packages that will be installed below.

- Python >=2.5
- python-setuptools
- GIT
- Swig
- Sqlite3
- libssl
- mysqlclient
- pq
- curl4 (with openssl)
- memcached

The package commands are listed below for common deployments.

#### Debian

    apt-get install git swig sqlite3 memcached lib{ssl,mysqlclient,pq,curl4-openssl}-dev python{,2.6-dev,-{ldap,setuptools}}


#### Ubuntu

    apt-get install git swig sqlite3 memcached lib{ssl,mysqlclient,pq,curl4-openssl}-dev python{,2.7-dev} python-{ldap,setuptools}


### Getting the Source Code

    git clone https://github.com/TireSwingSoftware/openassign-server.git
    cd openassign-server
    git checkout dev

### Creating a virtual environment **\*Optional\***

If you wish to keep the python packages for openassign-server separate from
the rest of the system (to prevent versioning issues) you may wish to
create a virtualenv.

    sudo easy_install virtualenv
    virtualenv /path/to/env
    cd !$
    source bin/activate


### Installing python package requirements

If you created a virtual environment, be sure to specify the path for pip.

    easy_install pip
    pip -E /path/to/env install -r requirements.txt

Otherwise

    easy_install pip
    pip -r requirements.txt


### Initial Configuration

Two files are provided which contain the majority of configuration options
for the system. These are *settings.py* and *local\_settings.py*.

#### settings.py

Contains mostly static Django settings which are not likely to change per
deployment.

**Note:** For development purposes you may wish to disable the vod service by
commenting out 'vod\_aws' in the INSTALLED\_APPS section.


#### local_settings.py

Contains settings which may change per deployment

A template for local\_settings.py exists for convenience and is called
*local\_settings.py.example*. Rename this file to local\_settings.py and
tune the settings as you require. Documentation is provided inline
with each option.

### Final steps

Run the following commands to perform the database initialization.

    ./manage.py resetdb
    ./manage.py setup


## Running the test suite

#### Local unit tests:

    ./manage.py test pr_services

#### Remote service tests:

 Settings are defined in **test_svc_settings.py** which can be copied from the
 **test_svc_settings.py.example** template file. These tests require running
  the server.

    ./manage.py runserver 127.0.0.1:12345
    ./tests_svc.py


