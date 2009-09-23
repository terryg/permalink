import os
import logging
import urllib
import wsgiref.handlers
import random
from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

PERMALINK = "permalink"

class GeneralCounterShardConfig(db.Model):
  """Tracks the number of shards for each named counter."""
  name = db.StringProperty(required=True)
  num_shards = db.IntegerProperty(required=True, default=20)

class GeneralCounterShard(db.Model):
  """Shards for each named counter"""
  name = db.StringProperty(required=True)
  count = db.IntegerProperty(required=True, default=0)
 
           
def get_count(name):
  """Retrieve the value for a given sharded counter.
 
  Parameters:
    name - The name of the counter 
  """
  total = memcache.get(name)
  if total is None:
    total = 0
    for counter in GeneralCounterShard.all().filter('name = ', name):
      total += counter.count
    memcache.add(name, str(total), 60)
  return total
 
def increment(name):
  """Increment the value for a given sharded counter.
 
  Parameters:
    name - The name of the counter 
  """
  config = GeneralCounterShardConfig.get_or_insert(name, name=name)
  def txn():
    index = random.randint(0, config.num_shards - 1)
    shard_name = name + str(index)
    counter = GeneralCounterShard.get_by_key_name(shard_name)
    if counter is None:
      counter = GeneralCounterShard(key_name=shard_name, name=name)
    counter.count += 1
    counter.put()
  db.run_in_transaction(txn)
  memcache.incr(name)
 
def increase_shards(name, num): 
  """Increase the number of shards for a given sharded counter.
  Will never decrease the number of shards.
 
  Parameters:
    name - The name of the counter
    num - How many shards to use
   
  """
  config = GeneralCounterShardConfig.get_or_insert(name, name=name)
  def txn():
    if config.num_shards < num:
      config.num_shards = num
      config.put()   
  db.run_in_transaction(txn)

class Permalink(db.Model):
  url = db.StringProperty(required=True)
  index = db.IntegerProperty(required=True)
  shortcut = db.StringProperty(required=True)

class PermalinkTracker(db.Model):
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
  if handler.request.path is '/':
    return handler.request.url[0:-1]
  pos = handler.request.url.find(handler.request.path)
  return handler.request.url[0:pos]

def post_permalink(url, alias):
  count = 0
  for link in Permalink.gql('WHERE url = :1', url):
    count += 1

  if count is 0:
    new_index = int(get_count(PERMALINK)) + 1

    def txn():
      shortcut = str(base_n_encode(new_index))

      logging.info('New index ' + str(new_index))
      logging.info('URL ' + url)
      logging.info('Shortcut ' + shortcut)
      logging.info('Alias ' + alias)
      new_link = Permalink(
        key_name = PERMALINK + str(new_index),
        index = new_index,
        url = url,
        shortcut = shortcut)
      new_link.put()

      logging.info('After put')
      logging.info(new_link.key())
    db.run_in_transaction(txn)          

    increment(PERMALINK)


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

    count = get_count("shortcut" + permalink.shortcut)
 
    do_render(self,'info.htm',{'count' : count, 'url' : permalink.url, 'shortcut' : permalink.shortcut})
  
class CreateHandler(webapp.RequestHandler):
  def get(self):
    do_render(self,'index.htm')

  def post(self):
    url = urllib.unquote(self.request.get('url'))
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
      total = get_count(PERMALINK)
      if do_render(self,self.request.path,{'total' : total}):
        return
      do_render(self,'index.htm',{'total' : total})
    else:
      increment("shortcut" + permalink.shortcut)
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
