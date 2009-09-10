import os
import logging
import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

GLOBAL_INDEX_PERMALINK = "permalink"

class GlobalIndex(db.Model):
  max_index = db.IntegerProperty(required=True,default=1)

class Permalink(db.Model):
  url = db.StringProperty(required=True)
  index = db.IntegerProperty(required=True)
  shortcut = db.StringProperty(required=True)

class PermalinkAlias(db.Model):
  link = db.ReferenceProperty(required=True)
  name = db.StringProperty(required=True)

class PermalinkCounter(db.Model):
  count = db.IntegerProperty(required=True,default=0)

class PermalinkTracker(db.Model):
  referrer = db.StringProperty(required=True)
  ip_address = db.StringProperty(required=True)

# Code adapted from: http://en.wikipedia.org/wiki/Base_36#Python_Conversion_Code
# This is base 62:
ALPHABETS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

def base_n_decode(s, alphabets=ALPHABETS):
    n = len(alphabets)
    rv = pos = 0
    charlist = list(s)
    charlist.reverse()
    for char in charlist:
        rv += alphabets.find(char) * n**pos
        pos += 1
    return rv

def base_n_encode(num, alphabets=ALPHABETS):
    n = len(alphabets)
    rv = ""
    while num != 0:
        rv = alphabets[num % n] + rv
        num /= n
    return rv

def get_domain(handler):
  pos = handler.request.url.find('http://')
  pos = handler.request.url.find('//')  
  return handler.request.url[0:pos]

def post_permalink(url, alias):
  count = 0
  for link in Permalink.gql('WHERE url = :1', url):
    count += 1

  if count is 0:
    def txn():
      link_index = GlobalIndex.get_by_key_name(GLOBAL_INDEX_PERMALINK)
      if link_index is None:
        link_index = GlobalIndex(key_name=GLOBAL_INDEX_PERMALINK)
      new_index = link_index.max_index
      link_index.max_index += 1
      link_index.put()

      shortcut = str(base_n_encode(new_index))

      logging.info('New index ' + str(new_index))
      logging.info('URL ' + url)
      logging.info('Shortcut ' + shortcut)
      logging.info('Alias ' + alias)
      new_link = Permalink(
        key_name = GLOBAL_INDEX_PERMALINK + str(new_index),
        parent = link_index,
        index = new_index,
        url = url,
        shortcut = shortcut)
      new_link.put()

      logging.info('After put')
      logging.info(new_link.key())
    db.run_in_transaction(txn)          

def do_render(handler, tname = 'index.htm', values = { }):
  temp = os.path.join(os.path.dirname(__file__), 'templates/' + tname)    
  if not os.path.isfile(temp):
    return False

  newval = dict(values)
  newval['path'] = handler.request.path
  newval['domain'] = get_domain(handler)

  outstr = template.render(temp, newval)
  handler.response.out.write(outstr)
  return True

class InfoHandler(webapp.RequestHandler):
  def get(self):
    logging.info("INFO HANDLER")
    logging.info("Request path: " + self.request.path);
    pos = self.request.path.rfind('/')
    path = self.request.path[pos+1:]
    logging.info("Request path w/o /: " + path)

    permalink = None
    for link in Permalink.gql('WHERE shortcut = :1', path):
      permalink = link

    counter = PermalinkCounter.get_by_key_name("shortcut" + permalink.shortcut)

    do_render(self,'info.htm',{'count' : counter.count, 'url' : permalink.url, 'shortcut' : permalink.shortcut})
  
class CreateHandler(webapp.RequestHandler):
  def get(self):
    do_render(self,'index.htm')

  def post(self):
    url = self.request.get('url')
    alias = self.request.get('alias')
    if url == '':
      do_render(self,
               'index.htm',
               {'error' : 'Blank URL ignored'})
      return

    post_permalink(url, alias)
    
    permalink = None
    for link in Permalink.gql('WHERE url = :1', url):
      permalink = link

    do_render(self, 'show.htm', {'url' : permalink.url,
                                 'shortcut' : permalink.shortcut,
                                  'domain' : get_domain(self)})

class MainHandler(webapp.RequestHandler):
  def get(self):      
    logging.info("Request path: " + self.request.path);
    path = self.request.path[1:]
    logging.info("Request path w/o /: " + path)

    permalink = None
    for link in Permalink.gql('WHERE shortcut = :1', path):
      logging.info("Found: " + link.url)
      permalink = link

    if permalink is None:
      if do_render(self,self.request.path):
        return
      do_render(self,'index.htm')
    else:
      counter = PermalinkCounter.get_by_key_name("shortcut" + permalink.shortcut)
      if counter is None:
        counter = PermalinkCounter(key_name="shortcut" + permalink.shortcut)
      counter.count += 1
      counter.put()
      self.redirect(permalink.url)
    
application = webapp.WSGIApplication([
  ('/create', CreateHandler),
  ('/info/.*', InfoHandler),
  ('/.*', MainHandler)],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
