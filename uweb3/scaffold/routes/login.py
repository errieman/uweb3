#!/usr/bin/python3
"""Request handlers for the uWeb3 project scaffold"""

import uweb3
from uweb3 import SqAlchemyPageMaker, PageMaker
from uweb3.pagemaker.new_login import Users, UserCookie, Test
from uweb3.pagemaker.new_decorators import checkxsrf
from uweb3 import globals

class UserPageMaker(PageMaker):
  """Holds all the request handlers for the application"""
    
  def Login(self):
    """Returns the index template"""
    globals.event_listener('test_event')
    globals.event_listener.remove('test_event', "TEST")
    scookie = UserCookie(self.secure_cookie_connection)
    if self.req.method == 'POST':
      try:
        if 'login' in scookie.cookiejar:
          return self.req.Redirect('/home', http_code=303)
        user = Users.FromName(self.connection, self.post.getfirst('username'))
        if Users.ComparePassword(self.post.getfirst('password'), user['password']):
          scookie.Create("login", {
                'user_id': user['id'],
                'premissions': 1,
                'data': {'data': 'data'}
                })
          return self.req.Redirect('/home', http_code=303)
        else:
          print('Wrong username/password combination')      
      except uweb3.model.NotExistError as e:
        Users.CreateNew(self.connection, { 'username': self.post.getfirst('username'), 'password' : self.post.getfirst('password')})
        print(e)  
    return self.parser.Parse('login.html')
