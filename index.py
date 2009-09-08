import os
import logging
import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

def doRender(handler, tname = 'index.htm', values = { }):
  temp = os.path.join(os.path.dirname(__file__), 'templates/' + tname)    
  if not os.path.isfile(temp):
    return False

  newval = dict(values)
  newval['path'] = handler.request.path
  
  outstr = template.render(temp, newval)
  handler.response.out.write(outstr)
  return True

class CreateHandler(webapp.RequestHandler):
  def get(self):
    doRender(self,'index.htm')

  def post(self):
    doRender(self,'show.htm')


class MainHandler(webapp.RequestHandler):
  def get(self):      
    if doRender(self,self.request.path):
      return
    doRender(self,'index.htm')

application = webapp.WSGIApplication(
                                     [('/.*', MainHandler)],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
