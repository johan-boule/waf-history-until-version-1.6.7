#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006 (ita)

import sys, os, string

alpha = string.letters + '_' + string.digits

accepted  = 'a'
ignored   = 'i'
undefined = 'u'
skipped   = 's'

trigs = {
'=' : '#',
'-' : '~',
'/' : '\\',
'!' : '|',
'\'': '^',
'(' : '[',
')' : ']',
'<' : '{',
'>' : '}',
}

punctuators_table = [
{'!': 43, '#': 45, '%': 22, '&': 30, ')': 50, '(': 49, '+': 11, '*': 18, '-': 14, 
 ',': 56, '/': 20, '.': 38, ';': 55, ':': 41, '=': 28, '<': 1, '?': 54, '>': 7, 
 '[': 47, ']': 48, '^': 36, '{': 51, '}': 52, '|': 33, '~': 53}, 
{'=': 6, ':': 5, '%': 4, '<': 2, '$$': '<'}, 
{'$$': '<<', '=': 3}, 
{'$$': '<<='}, 
{'$$': '<%'}, 
{'$$': '<:'}, 
{'$$': '<='}, 
{'$$': '>', '=': 10, '>': 8}, 
{'$$': '>>', '=': 9}, 
{'$$': '>>='}, 
{'$$': '>='},
{'$$': '+', '+': 12, '=': 13}, 
{'$$': '++'}, 
{'$$': '+='}, 
{'=': 17, '-': 15, '$$': '-', '>': 16}, 
{'$$': '--'}, 
{'$$': '->'}, 
{'$$': '-='}, 
{'$$': '*', '=': 19}, 
{'$$': '*='}, 
{'$$': '/', '=': 21}, 
{'$$': '/='}, 
{'$$': '%', ':': 23, '=': 26, '>': 27}, 
{'$$': '%:', '%': 24}, 
{':': 25}, 
{'$$': '%:%:'}, 
{'$$': '%='}, 
{'$$': '%>'}, 
{'$$': '=', '=': 29}, 
{'$$': '=='}, 
{'$$': '&', '=': 32, '&': 31}, 
{'$$': '&&'}, 
{'$$': '&='}, 
{'$$': '|', '=': 35, '|': 34}, 
{'$$': '||'}, 
{'$$': '|='}, 
{'$$': '^', '=': 37}, 
{'$$': '^='}, 
{'$$': '.', '.': 39}, 
{'.': 40}, 
{'$$': '...'}, 
{'$$': ':', '>': 42}, 
{'$$': ':>'}, 
{'$$': '!', '=': 44}, 
{'$$': '!='}, 
{'#': 46, '$$': '#'}, 
{'$$': '##'}, 
{'$$': '['}, 
{'$$': ']'}, 
{'$$': '('}, 
{'$$': ')'}, 
{'$$': '{'}, 
{'$$': '}'}, 
{'$$': '~'}, 
{'$$': '?'}, 
{'$$': ';'}, 
{'$$': ','}
]

preproc_table = [
{'e': 16, 'd': 26, 'i': 1, 'p': 37, 'u': 32, 'w': 46}, 
{'f': 8, 'n': 2}, 
{'c': 3}, 
{'l': 4}, 
{'u': 5}, 
{'d': 6}, 
{'e': 7}, 
{'$$': 'include'}, 
{'$$': 'if', 'd': 9, 'n': 12}, 
{'e': 10}, 
{'f': 11}, 
{'$$': 'ifdef'}, 
{'d': 13}, 
{'e': 14}, 
{'f': 15}, 
{'$$': 'ifndef'}, 
{'r': 53, 'l': 17, 'n': 22}, 
{'i': 20, 's': 18}, 
{'e': 19}, 
{'$$': 'else'}, 
{'f': 21}, 
{'$$': 'elif'}, 
{'d': 23}, 
{'i': 24}, 
{'f': 25}, 
{'$$': 'endif'}, 
{'e': 27}, 
{'b': 43, 'f': 28}, 
{'i': 29}, 
{'n': 30}, 
{'e': 31}, 
{'$$': 'define'}, 
{'n': 33}, 
{'d': 34}, 
{'e': 35}, 
{'f': 36}, 
{'$$': 'undef'}, 
{'r': 38}, 
{'a': 39}, 
{'g': 40}, 
{'m': 41}, 
{'a': 42}, 
{'$$': 'pragma'}, 
{'u': 44}, 
{'g': 45}, 
{'$$': 'debug'}, 
{'a': 47}, 
{'r': 48}, 
{'n': 49}, 
{'i': 50}, 
{'n': 51}, 
{'g': 52}, 
{'$$': 'warning'}, 
{'r': 54}, 
{'o': 55}, 
{'r': 56}, 
{'$$': 'error'}]

def parse_token(stuff, table):
	c = stuff.next()
	stuff.back(1)
	if not (c in table[0]):
		#print "error, character is not in table", c
		return 0
	pos = 0
	while stuff.good():
		c = stuff.next()
		if c in table[pos]:
			pos = table[pos][c]
		else:
			stuff.back(1)
			try: return table[pos]['$$']
			except: return 0
			# lexer error
	return table[pos]['$$']

def get_punctuator_token(stuff):
	return parse_token(stuff, punctuators_table)

def get_preprocessor_token(stuff):
	return parse_token(stuff, preproc_table)

class filter:
	def __init__(self):
		self.fn     = ''
		self.i      = 0
		self.max    = 0
		self.txt    = ""
		self.buf    = []
		#self.debug = []

	def next(self):
		ret = self.txt[self.i]
		# trigraphs can be filtered straight away
		if ret == '?':
			if self.txt[self.i+1] == '?':
				try:
					car = trigs[self.txt[self.i+2]]
					self.i += 3
					#self.debug.append(car)
					return car
				except:
					pass
		# unterminated lines can be eliminated too
		elif ret == '\\':
			try:
				if self.txt[self.i+1] == '\n':
					self.i += 2
					return self.next()
				elif self.txt[self.i+1] == '\r':
					if self.txt[self.i+2] == '\n':
						self.i += 3
						return self.next()
				else:
					pass
			except:
				pass
		elif ret == '\r':
			if self.txt[self.i+1] == '\n':
				self.i += 2
				#self.debug.append('\n')
				return '\n'
		self.i += 1
		#self.debug.append(ret)
		return ret

	def good(self):
		return self.i < self.max

	def initialize(self, filename):
		self.fn = filename
		f=open(filename, "r")
		self.txt = f.read()
		f.close()

		self.i = 0
		self.max = len(self.txt)

	def start(self, filename):
		self.initialize(filename)
		while self.good():
			c = self.next()
			#print self.buf.append(c)
			#continue
			if c == ' ' or c == '\t' or c == '\n':
				continue
			elif c == '#':
				self.preprocess()
			elif c == '%':
				d = self.next()
				if d == ':':
					self.preprocess()
				else:
					self.eat_line()
			elif c == '/':
				self.skip_comment()
			elif c == '"':
				self.skip_string()
				self.eat_line()
			elif c == '\'':
				self.skip_char()
				self.eat_line()

	def get_cc_comment(self):
		c = self.next()
		while c != '\n': c = self.next()

	def get_c_comment(self):
		c = self.next()
		prev = 0
		while self.good():
			if c == '*':
				prev = 1
			elif c == '/':
				if prev: break
			else:
				prev = 0
			c = self.next()

	def skip_comment(self):
		c = self.next()
		if c == '*': self.get_c_comment()
		elif c == '/': self.get_cc_comment()

	def skip_char(self, store=0):
		c = self.next()
		if store: self.buf.append(c)
		# skip one more character if there is a backslash '\''
		if c == '\\':
			c = self.next()
			if store: self.buf.append(c)
		c = self.next()
		if store: self.buf.append(c)
		if c != '\'': print "uh-oh, invalid character"

	def skip_string(self, store=0):
		c=''
		while self.good():
			p = c
			c = self.next()
			if store: self.buf.append(c)
			if c == '"':
				cnt = 0
				while 1:
					#print "cntcnt = ", str(cnt), self.txt[self.i-2-cnt]
					if self.txt[self.i-2-cnt] == '\\': cnt+=1
					else: break
				#print "cnt is ", str(cnt)
				if (cnt%2)==0: break

			#if c == '\n':
			#	print 'uh-oh, invalid line >'+c+'< '+self.fn
			#	raise "".join(self.debug)
			#	break

	def eat_line(self):
		while self.good():
			c = self.next()
			if c == '\n':
				break
			elif c == '"':
				self.skip_string()
			elif c == '\'':
				self.skip_char()
			elif c == '/':
				self.skip_comment()

	def preprocess(self):
		#self.buf.append('#')
		# skip whitespaces like "#  define"
		while self.good():
			car = self.txt[self.i]
			if car == ' ' or car == '\t': self.i+=1
			else: break	

		while self.good():
			c = self.next()
			if c == '\n':
				self.buf.append(c)
				break
			elif c == '"':
				self.buf.append(c)
				self.skip_string(store=1)
			elif c == '\'':
				self.buf.append(c)
				self.skip_char(store=1)
			elif c == '/':
				self.skip_comment()
			else:
				self.buf.append(c)

class cparse:
	def __init__(self, paths):
		#self.lines = txt.split('\n')
		self.lines = []
		self.i     = 0
		self.txt   = ''
		self.max   = 0
		self.buf   = []

		self.defs  = {}
		self.state = []

		# include paths
		self.paths = paths
		self.pathcontents = {}

		self.deps  = []
		self.deps_paths = []

	def tryfind(self, filename):
		for p in self.paths:
			if not p in self.pathcontents:
				self.pathcontents[p] = os.listdir(p)
			if filename in self.pathcontents[p]:
				#print "file %s found in path %s" % (filename, p)
				np = os.path.join(p, filename)
				self.addlines(np)
				self.deps_paths.append(np)

	def addlines(self, filepath):
		try:
			stuff = filter()
			stuff.start(filepath)
			self.lines += (''.join(stuff.buf)).split('\n')
		except:
			print "parsing %s failed" % filepath
			raise

	def start(self, filename):
		self.addlines(filename)

		for line in self.lines:
			if not line: continue
			self.txt = line
			self.i   = 0
			self.max = len(line)
			try:
				self.process_line()
			except:
				print "line parsing failed >%s<" % line
				raise
	def back(self, c):
		self.i -= c

	def next(self):
		car = self.txt[self.i]
		self.i += 1
		return car

	def good(self):
		return self.i < self.max

	def skip_spaces(self):
		# skip the spaces
		while self.good():
			c = self.next()
			if c == ' ' or c == '\t': continue
			else:
				self.i -= 1
				break

	def isok(self):
		if not self.state: return 1
		for tok in self.state:
			if tok == skipped or tok == ignored: return None
		return 1

	def process_line(self):
		type = ''
		l = len(self.txt)
		token = get_preprocessor_token(self)
		if not token: return

		if token == 'endif':
			self.state.pop(0)
		elif token[0] == 'i' and token != 'include':
			self.state = [undefined] + self.state

		#print "token before ok is ", token

		# skip lines when in a dead block
		# wait for the endif
		if not self.isok(): return

		#print "token is ", token

		if token == 'if':
			self.state[0] = ignored
			pass
		elif token == 'ifdef':
			ident = self.get_name()
			if ident in self.defs: self.state[0] = accepted
			else: self.state[0] = ignored
		elif token == 'ifndef':
			ident = self.get_name()
			if ident in self.defs: self.state[0] = ignored
			else: self.state[0] = accepted
		elif token == 'include':
			(type, body) = self.get_include()

			print "include found %s    (%s) " % (body, type)
			if type == '"':
				self.deps.append(body)
				self.tryfind(body)

		elif token == 'elif':
			if self.state[0] == accepted:
				self.state[0] = skipped
			elif self.state[0] == ignored:
				# TODO: do the job here
				if 0:
					self.state[0] = accepted
				else:
					# let another 'e' treat this case
					pass
				pass
			else:
				pass
		elif token == 'else':
			if self.state[0] == accepted: self.state[0] = skipped
			elif self.state[0] == ignored: self.state[0] = accepted
		elif token == 'endif':
			pass
		elif token == 'define':
			name = self.get_name()
			args = self.get_args()
			body = self.get_body()
			#print "define %s (%s) { %s }" % (name, str(args), str(body))
			if not args:
				self.defs[name] = body
			else:
				# TODO handle macros
				pass
		elif token == 'undef':
			name = self.get_name()
			if name:
				if name in self.defs:
					self.defs.__delitem__(name)
				#print "undef %s" % name

	def get_include(self):
		self.skip_spaces()
		delimiter = self.next()
		if delimiter == '"':
			buf = []
			while self.good():
				c = self.next()
				if c == delimiter: break
				buf.append(c)
			return (delimiter, "".join(buf))
		elif delimiter == "<":
			buf = []
			while self.good():
				c = self.next()
				if c == '>': break
				buf.append(c)
			return (delimiter, "".join(buf))
		else:
			self.i -= 1
			return ('', self.get_body())

	def get_name(self):
		ret = []
		self.skip_spaces()
		# get the first word found
		while self.good():
			c = self.next()
			if c != ' ' and c != '\t' and c != '(': ret.append(c)
			else:
				self.i -= 1
				break
		return "".join(ret)

	def get_args(self):
		ret = []
		self.skip_spaces()
		if not self.good(): return None

		c = self.next()
		if c != '(':
			self.i -= 1
			return None
		buf = []
		while self.good():
			c = self.next()
			if c == ' ' or c == '\t': continue
			elif c == ',':
				ret.append("".join(buf))
				buf = []
			elif c == '.':
				if self.txt[self.i:self.i+2]=='..':
					buf += ['.', '.', '.']
					ret.append("".join(buf))
					self.i += 2
			elif c == ')':
				break
			else:
				buf.append(c)
		return ret

	def get_body(self):
		buf = []
		self.skip_spaces()
		while self.good():
			c = self.next()
			self.back(1)

			#print "considering ", c

			if c == ' ' or c == '\t':
				self.i += 1
				continue
			elif c == '"':
				self.i += 1
				r = self.get_string()
				buf.append( ['string', r] )
			elif c == '\'':
				self.i += 1
				r = self.get_char()
				buf.append( ['char', r] )
			elif c in string.digits:
				num = self.get_number()
				buf.append( ['number', num] )
			elif c in alpha: 
				r = self.get_ident()
				buf.append( ['ident', r] )
			else:
				r = get_punctuator_token(self)
				if r:
					#print "r is ", r
					buf.append( ['punc', r])
				#else:
				#	print "NO PUNCTUATOR FOR ", c

		#def end(l):
		#	return l[1]
		#print buf
		#return "".join( map(end, buf) )
		return buf

	def get_char(self):
		buf = []
		c = self.next()
		buf.append(c)
		# skip one more character if there is a backslash '\''
		if c == '\\':
			c = self.next()
			buf.append(c)
		c = self.next()
		#buf.append(c)
		if c != '\'': print "uh-oh, invalid character", c

		return ''.join(buf)

	def get_string(self):
		buf = []
		c=''
		while self.good():
			p = c
			c = self.next()
			if c == '"':
				cnt = 0
				while 1:
					#print "cntcnt = ", str(cnt), self.txt[self.i-2-cnt]
					if self.txt[self.i-2-cnt] == '\\': cnt+=1
					else: break
				#print "cnt is ", str(cnt)
				if (cnt%2)==0: break
				else: buf.append(c)
			else:
				buf.append(c)

		return ''.join(buf)

	def get_number(self):
		buf =[]
		while self.good():
			c = self.next()
			if c in string.digits:
				buf.append(c)
			else:
				self.i -= 1
				break
		return ''.join(buf)
	def get_ident(self):
		buf = []
		while self.good():
			c = self.next()
			if c in alpha:
				buf.append(c)
			else:
				self.i -= 1
				break
		return ''.join(buf)

	def eval(self, stuff):
		#self.defs
		return 0

try:
	arg = sys.argv[1]
except:
	arg = "file.c"

paths = ['.']
gruik = cparse(paths)
gruik.start(arg)
print "we have found the following dependencies"
print gruik.deps
print gruik.deps_paths

# because of the includes system, it is necessary to do the preprocessing in at least two steps:
# * 1 filter the comments and output the preprocessing lines
# * 2 interpret the preprocessing lines, jumping on the headers during the process


