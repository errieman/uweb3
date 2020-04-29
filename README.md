# New and improved: µWeb3

Since µWeb inception we have used it for many projects, and while it did its job, there were plenty of rough edges. This new version intends to remove those and pull it into the current age.

# Notable changes

* wsgi complaint interface
* python3 native
* Better handling of strings and automatic escaping
* More options for template engines
* More options for SQL / database engines


## Example projects

The following example applications for uWeb3 exist:

* [uWeb3-info](https://github.com/edelooff/uWeb3-info): This demonstrates most µWeb3 features, and gives you examples on how to use most of them.
* [uWeb3-logviewer](https://github.com/edelooff/uWeb3-logviewer): This allows you to view and search in the logs generated by all µWeb and µWeb3 applications.

# µWeb3 installation

The easiest and quickest way to install µWeb3 is using Python's `virtualenv`. Install using the setuptools installation script, which will automatically gather dependencies.

```bash
# Set up the Python3 virtualenv
python3 -m venv env
source env/bin/activate

# Install uWeb3
python3 setup.py install

# Or you can install in development mode which allows easy modification of the source:
python3 setup.py develop

cd uweb3/scaffold

python3 serve.py
```

## Ubuntu issues
On some ubuntu setups venv is broken and therefore does not install the activation scripts.

```bash
# Set up the Python3 virtualenv on Ubuntu
python3 -m venv --without-pip env
source env/bin/activate
curl https://bootstrap.pypa.io/get-pip.py | python
deactivate
source env/bin/activate

# then proceed to install µWeb3 like before.
```

# µWeb3 database setup

Setting up a database connection with µWeb3 is easy, navigate to the settings.ini file in the scaffold folder and add the following fields to the file:
```
[mysql] OR [sqlite]
host = 'host'
user = 'username'
password = 'pass'
database = 'dbname'
```
To access your database connection simply use the connection attribute in any class that inherits from PageMaker.

# Config settings
If you are working on µWeb3 core make sure to enable the following setting in the config:
```
[development]
dev = True
```
This makes sure that µWeb3 restarts every time you modify something in the core of the framework aswell.

µWeb3 has inbuild XSRF protection. You can import it from uweb3.pagemaker.new_decorators checkxsrf.
This is a decorator and it will handle validation and generation of the XSRF.
The only thing you have to do is add the ```{{ xsrf [xsrf]}}``` tag into a form.
The xsrf token is accessible in any pagemaker with self.xsrf.  

# Routing
The default way to create new routes in µWeb3 is to create a folder called routes.
In the routes folder create your pagemaker class of choice, the name doesn't matter as long as it inherits from PageMaker.
After creating your pagemaker be sure to add the route endpoint to routes list in base/__init__.py.

# New
- In uweb3 __init__ a class called HotReload
- In pagemaker __init__:
  - A classmethod called loadModules that loads all pagemaker modules inheriting from PageMaker class
  - A XSRF class
    - Generates a xsrf token and creates a cookie if not in place
    - Validates the xsrf token in a post request if the enable_xsrf flag is set in the config.ini
- In requests:
  - Self.method attribute
  - self.post.form attribute. This is the post request as a dict, includes blank values.
  - Method called Redirect #Moved from the response class to the request class so cookies that are set before a redirect are actually set.
  - Method called DeleteCookie
  - A if statement that checks string like cookies and raises an error if the size is equal or bigger than 4096 bytes.
  - AddCookie method, edited this and the response class to handle the setting of multiple cookies. Previously setting multiple cookies with the       Set-Cookie header would make the last cookie the only cookie.
- In pagemaker/new_login Users class:
  - Create user
  - Find user by name
  - Create a cookie with userID + secret
  - Validate if user messed with given cookie and render it useless if so
- In pagemaker/new_decorators:
  - Loggedin decorator that validates if user is loggedin based on cookie with userid
  - Checkxsrf decorator that checks if the incorrect_xsrf_token flag is set
- In templatepaser:
  - A function called _TemplateConstructXsrf that generates a hidden input field with the supplied value: {{ xsrf [xsrf_variable]}}
- In libs/sqltalk
  - Tried to make sqltalk python3 compatible by removing references to: long, unicode and basestring
  - So far so good but it might crash on functions that I didn't use yet


# Login validation
Instead of using sessions to keep track of logged in users µWeb3 uses secure cookies. So how does this work?
When a user logs in for the first time there is no cookie in place, to set one we go through the normal process of validating a user and loggin in.

To create a secure cookie inherit from the Model.SecureCookie. The SecureCookie class has a few build in methods, Create, Update and Delete.
To create a new cookie make use of the `Create` method, it works the same ass the AddCookie method.

If you want to see which cookies are managed by the SecureCookie class you can call the session attribute.
The session attribute decodes all managed cookies and can be used to read them.

# SQLAlchemy
SQLAlchemy is available in uWeb3 by using the SqAlchemyPageMaker instead of the regular pagemaker.
SQLAlchemy comes with most of the methods that are available in the default model.Record class, however because SQLAlchemy works like an ORM
there are some adjustments. Instead of inheriting from dict the SQLAlchemy model.Record inherits from object, meaning you can no longer use
dict like functions such as get and set. Instead the model is accessible by the columns defined in the class you want to create.

The SQLAlchemy model.Record class makes use of the session attribute accessible in the SqAlchemyPageMaker.
The session keeps track of all queries to the database and comes with some usefull features.

An example of a few usefull features:
`session.new`: The set of all instances marked as ‘new’ within this Session.
`session.dirty`: Instances are considered dirty when they were modified but not deleted.
`session.deleted`: The set of all instances marked as ‘deleted’ within this Session
the rest can be found at https://docs.sqlalchemy.org/en/13/orm/session_api.html

Objects in the session will only be updated/created in the actuall database on session.commit()/session.flush().

Defining classes that represent a table is different from how we used to do it in uWeb2.
SQLAlchemy requires you to define all columns from the table that you want to use.
For example, creating a class that represents the user table could look like this:

```
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
  __tablename__ = 'users'

  id = Column(Integer, primary_key=True)
  username = Column(String, nullable=False, unique=True)
  password = Column(String, nullable=False)
```
We can now use this class to query our users table in the SqAlchemyPageMaker to get the user with id 1:
`self.session.query(User).filter(User.id == 1).first() `
or to list all users:
`self.session.query(User).all()`
uWeb3's SQLAlchemy model.Record has almost the same functionality as uWeb3's regular model.Record so we can simplify our code to this:

```
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

#Notice how we load in the uweb3.model.AlchemyRecord class to gain access to all sorts of functionality
class User(uweb3.model.AlchemyRecord, Base):
  __tablename__ = 'users'

  id = Column(Integer, primary_key=True)
  username = Column(String, nullable=False, unique=True)
  password = Column(String, nullable=False)
```  
We can now query the users table like this:
```
User.FromPrimary(self.session, 1)
>>> User({'id': 1, 'username': 'username', 'password': 'password'})
```
Or to get a list of all users:
```
User.List(self.session, conditions=[User.id <= 2])
>>> [
  User({'id': 1, 'username': 'name', 'password': 'password'}),
  User({'id': 2, 'username': 'user2', 'password': 'password'})
  ]
```

Now if we want to automatically load related tables we can set it up like this:

```
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()

class User(uweb3.model.AlchemyRecord, Base):
  __tablename__ = 'users'

  id = Column(Integer, primary_key=True)
  username = Column(String, nullable=False, unique=True)
  password = Column(String, nullable=False)
  userinfoid = Column('userinfoid', Integer, ForeignKey('UserInfo.id'))
  userdata = relationship("UserInfo",  lazy="select")

  def __init__(self, *args, **kwargs):
    super(User, self).__init__(*args, **kwargs)

class UserInfo(uweb3.model.AlchemyRecord, Base):
  __tablename__ = 'UserInfo'

  id = Column(Integer, primary_key=True)
  name = Column(String, unique=True)
```
Now the UserInfo table will be loaded on the `userinfoid` attribute, but only after we try and access
this key a seperate query is send to retrieve the related information.
SQLAlchemy's lazy loading is fast but should be avoided while in loops. Take a look at SQLAlchemys documentation for optimal use.
