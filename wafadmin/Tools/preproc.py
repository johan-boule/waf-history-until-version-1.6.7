#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2006-2008 (ita)

#C/C++ preprocessor for finding dependencies
#TODO: more varargs, pragma once

import re, sys, os, string
if __name__ == '__main__':
	sys.path = ['.', '..'] + sys.path
import Logs, Build, Utils
from Logs import debug, error
import traceback

class PreprocError(Utils.WafError):
	pass

POPFILE = '-'

go_absolute = 0
"set to 1 to track headers on files in /usr/include - else absolute paths are ignored"

standard_includes = ['/usr/include']
if sys.platform == "win32":
	standard_includes = []

use_trigraphs = 0
'apply the trigraph rules first'

strict_quotes = 0
"Keep <> for system includes (do not search for those includes)"

g_optrans = {
'not':'!',
'and':'&&',
'bitand':'&',
'and_eq':'&=',
'or':'||',
'bitor':'|',
'or_eq':'|=',
'xor':'^',
'xor_eq':'^=',
'compl':'~',
}
"these ops are for c++, to reset, set an empty dict"

# ignore #warning and #error
re_lines = re.compile(\
	'^[ \t]*(#|%:)[ \t]*(ifdef|ifndef|if|else|elif|endif|include|import|define|undef|pragma)[ \t]*(.*)\r*$',
	re.IGNORECASE | re.MULTILINE)

# Reasons for using the Waf preprocessor by default
# 1. the preprocessing is performed once for the clean build, and each time a source file changes (fast)
# 2. unnecessary rebuilds might occur (#include in comments)
# 3. some includes use the preprocessor, for example #include A()
# 4. include guards might not be taken into account, resulting in infinite loops
# 5. the bugs in the waf preprocessor are usually fixed quickly
#
# if you think your project does not need it, use this regexp to catch all includes
#re_lines = re.compile('^[ \t]*(#|%:)[ \t]*(include|import)[ \t]*(.*)\r*$', re.IGNORECASE | re.MULTILINE)

re_mac = re.compile("^[a-zA-Z_]\w*")
re_fun = re.compile('^[a-zA-Z_][a-zA-Z0-9_]*[(]')
re_pragma_once = re.compile('^\s*once\s*', re.IGNORECASE)
re_nl = re.compile('\\\\\r*\n', re.MULTILINE)
re_cpp = re.compile(\
	r"""(/\*[^*]*\*+([^/*][^*]*\*+)*/)|//[^\n]*|("(\\.|[^"\\])*"|'(\\.|[^'\\])*'|.[^/"'\\]*)""",
	re.MULTILINE)
trig_def = [('??'+a, b) for a, b in zip("=-/!'()<>", r'#~\|^[]{}')]
chr_esc = {'0':0, 'a':7, 'b':8, 't':9, 'n':10, 'f':11, 'v':12, 'r':13, '\\':92, "'":39}

NUM   = 'i'
OP    = 'O'
IDENT = 'T'
STR   = 's'
CHAR  = 'c'

tok_types = [NUM, STR, IDENT, OP]
exp_types = [
	r"""0[xX](?P<hex>[a-fA-F0-9]+)(?P<qual1>[uUlL]*)|L*?'(?P<char>(\\.|[^\\'])+)'|(?P<n1>\d+)[Ee](?P<exp0>[+-]*?\d+)(?P<float0>[fFlL]*)|(?P<n2>\d*\.\d+)([Ee](?P<exp1>[+-]*?\d+))?(?P<float1>[fFlL]*)|(?P<n4>\d+\.\d*)([Ee](?P<exp2>[+-]*?\d+))?(?P<float2>[fFlL]*)|(?P<oct>0*)(?P<n0>\d+)(?P<qual2>[uUlL]*)""",
	r'L?"([^"\\]|\\.)*"',
	r'[a-zA-Z_]\w*',
	r'%:%:|<<=|>>=|\.\.\.|<<|<%|<:|<=|>>|>=|\+\+|\+=|--|->|-=|\*=|/=|%:|%=|%>|==|&&|&=|\|\||\|=|\^=|:>|!=|##|[\(\)\{\}\[\]<>\?\|\^\*\+&=:!#;,%/\-\?\~\.]',
]
re_clexer = re.compile('|'.join(["(?P<%s>%s)" % (name, part) for name, part in zip(tok_types, exp_types)]), re.M)

accepted  = 'a'
ignored   = 'i'
undefined = 'u'
skipped   = 's'

def repl(m):
	s = m.group(1)
	if s is not None: return ' '
	s = m.group(3)
	if s is None: return ''
	return s

def filter_comments(filename):
	# return a list of tuples : keyword, line
	f = open(filename, "r")
	code = f.read()
	f.close()
	if use_trigraphs:
		for (a, b) in trig_def: code = code.split(a).join(b)
	code = re_nl.sub('', code)
	code = re_cpp.sub(repl, code)
	return [(m.group(2), m.group(3)) for m in re.finditer(re_lines, code)]

prec = {}
# op -> number, needed for such expressions:   #if 1 && 2 != 0
ops = ['* / %', '+ -', '<< >>', '< <= >= >', '== !=', '& | ^', '&& ||', ',']
for x in range(len(ops)):
	syms = ops[x]
	for u in syms.split():
		prec[u] = x

def reduce_nums(val_1, val_2, val_op):
	#print val_1, val_2, val_op
	# pass two values, return a value

	# now perform the operation, make certain a and b are numeric
	try:    a = 0 + val_1
	except TypeError: a = int(val_1)
	try:    b = 0 + val_2
	except TypeError: b = int(val_2)

	d = val_op
	if d == '%':  c = a%b
	elif d=='+':  c = a+b
	elif d=='-':  c = a-b
	elif d=='*':  c = a*b
	elif d=='/':  c = a/b
	elif d=='^':  c = a^b
	elif d=='|':  c = a|b
	elif d=='||': c = int(a or b)
	elif d=='&':  c = a&b
	elif d=='&&': c = int(a and b)
	elif d=='==': c = int(a == b)
	elif d=='!=': c = int(a != b)
	elif d=='<=': c = int(a <= b)
	elif d=='<':  c = int(a < b)
	elif d=='>':  c = int(a > b)
	elif d=='>=': c = int(a >= b)
	elif d=='^':  c = int(a^b)
	elif d=='<<': c = a<<b
	elif d=='>>': c = a>>b
	else: c = 0
	return c

def reduce_eval(lst):
	"""take a list of tokens and output true or false (#if/#elif conditions)"""
	# TODO this will not handle precedence rules, ternary operators, .. but it works
	try:
		return (NUM, str(eval(stringize(lst))))
	except:
		return (NUM, '0')

def stringize(lst):
	"""use for converting a list of tokens to a string"""
	lst = [str(v2) for (p2, v2) in lst]
	return "".join(lst)

def paste_tokens(t1, t2):
	"""
	here is what we can paste:
	 a b
	 > =
	 a 2
	"""
	p1 = None
	if t1[0] == OP and t2[0] == OP:
		p1 = OP
	elif t1[0] == IDENT and (t2[0] == IDENT or t2[0] == NUM):
		p1 = IDENT
	elif t1[0] == NUM and t2[0] == NUM:
		p1 = NUM
	if not p1:
		raise PreprocError('tokens do not make a valid paste %r and %r' % (t1, t2))
	return (p1, t1[1] + t2[1])

def reduce_tokens(lst, defs, ban=[]):
	i = 0

	while i < len(lst):
		(p, v) = lst[i]

		if p == IDENT and v in defs:

			# tokenize on demand
			if isinstance(defs[v], str):
				a, b = extract_macro(defs[v])
				defs[v] = b
			macro_def = defs[v]
			to_add = macro_def[1]

			if not macro_def[0]:
				# macro without arguments
				del lst[i]
				for x in xrange(len(to_add)):
					lst.insert(i, to_add[x])
					i += 1
			else:
				# collect the arguments for the funcall

				args = []
				del lst[i]

				if i >= len(lst):
					raise PreprocError("expected '(' after %r (got nothing)" % v)

				(p2, v2) = lst[i]
				if p2 != OP or v2 != '(':
					raise PreprocError("expected '(' after %r" % v)

				del lst[i]

				one_param = []
				count_paren = 0
				while i < len(lst):
					p2, v2 = lst[i]

					del lst[i]
					if p2 == OP and count_paren == 0:
						if v2 == '(':
							one_param.append((p2, v2))
							count_paren += 1
						elif v2 == ')':
							if one_param: args.append(one_param)
							break
						elif v2 == ',':
							if not one_param: raise PreprocError("empty param in funcall %s" % p)
							args.append(one_param)
							one_param = []
						else:
							one_param.append((p2, v2))
					else:
						one_param.append((p2, v2))
						if   v2 == '(': count_paren += 1
						elif v2 == ')': count_paren -= 1
				else:
					raise PreprocError('malformed macro')

				# substitute the arguments within the define expression
				accu = []
				arg_table = macro_def[0]
				j = 0
				while j < len(to_add):
					(p2, v2) = to_add[j]

					if p2 == OP and v2 == '#':
						# stringize is for arguments only
						if j+1 < len(to_add) and to_add[j+1][0] == IDENT and to_add[j+1][1] in arg_table:
							toks = args[arg_table[to_add[j+1][1]]]
							accu.append((STR, stringize(toks)))
							j += 1
						else:
							accu.append((p2, v2))
					elif p2 == OP and v2 == '##':
						# token pasting, how can man invent such a complicated system?
						if accu and j+1 < len(to_add):
							# we have at least two tokens

							t1 = accu[-1]

							if to_add[j+1][0] == IDENT and to_add[j+1][1] in arg_table:
								toks = args[arg_table[to_add[j+1][1]]]

								if toks:
									accu[-1] = paste_tokens(t1, toks[0]) #(IDENT, accu[-1][1] + toks[0][1])
									accu.extend(toks[1:])
								else:
									# error, case "a##"
									accu.append((p2, v2))
									accu.extend(toks)
							elif to_add[j+1][0] == IDENT and to_add[j+1][1] == '__VA_ARGS__':
								# TODO not sure
								# first collect the tokens
								va_toks = []
								st = len(macro_def[0])
								pt = len(args)
								for x in args[pt-st+1:]:
									va_toks.extend(x)
									va_toks.append((OP, ','))
								if va_toks: va_toks.pop() # extra comma
								if len(accu)>1:
									(p3, v3) = accu[-1]
									(p4, v4) = accu[-2]
									if v3 == '##':
										# remove the token paste
										accu.pop()
										if v4 == ',' and pt < st:
											# remove the comma
											accu.pop()
								accu += va_toks
							else:
								accu[-1] = paste_tokens(t1, to_add[j+1])

							j += 1
						else:
							# invalid paste, case    "##a" or "b##"
							accu.append((p2, v2))

					elif p2 == IDENT and v2 in arg_table:
						toks = args[arg_table[v2]]
						reduce_tokens(toks, defs, ban+[v])
						accu.extend(toks)
					else:
						accu.append((p2, v2))

					j += 1


				reduce_tokens(accu, defs, ban+[v])

				for x in xrange(len(accu)-1, -1, -1):
					lst.insert(i, accu[x])

		i += 1


def eval_macro(lst, adefs):
	# look at the result, and try to return a 0/1 result
	reduce_tokens(lst, adefs, [])
	if not lst: raise PreprocError("missing tokens to evaluate")
	(p, v) = reduce_eval(lst)
	return int(v) != 0

class c_parser(object):
	def __init__(self, nodepaths=None, defines=None):
		#self.lines = txt.split('\n')
		self.lines = []

		if defines is None:
			self.defs  = {}
		else:
			self.defs  = dict(defines) # make a copy
		self.state = []

		self.env   = None # needed for the variant when searching for files

		self.count_files = 0
		self.currentnode_stack = []

		self.nodepaths = nodepaths or []

		self.nodes = []
		self.names = []

		# file added
		self.curfile = ''
		self.ban_includes = []

	def tryfind(self, filename):
		self.curfile = filename

		# for msvc it should be a for loop on the whole stack
		found = self.currentnode_stack[-1].find_resource(filename)

		for n in self.nodepaths:
			if found:
				break
			found = n.find_resource(filename)

		if not found:
			if not filename in self.names:
				self.names.append(filename)
		else:
			self.nodes.append(found)
			if filename[-4:] != '.moc':
				self.addlines(found)
		return found

	def addlines(self, node):

		self.currentnode_stack.append(node.parent)
		filepath = node.abspath(self.env)

		self.count_files += 1
		if self.count_files > 30000: raise PreprocError("recursion limit exceeded, bailing out")
		pc = self.parse_cache
		debug('preproc: reading file %r' % filepath)
		try:
			lns = pc[filepath]
		except KeyError:
			pass
		else:
			self.lines = lns + self.lines
			return

		try:
			lines = filter_comments(filepath)
			lines.append((POPFILE, ''))
			pc[filepath] = lines # cache the lines filtered
			self.lines = lines + self.lines
		except IOError:
			raise PreprocError("could not read the file %s" % filepath)
		except Exception:
			if Logs.verbose > 0:
				error("parsing %s failed" % filepath)
				traceback.print_exc()

	def start(self, node, env):
		debug('preproc: scanning %s (in %s)' % (node.name, node.parent.name))

		self.env = env
		variant = node.variant(env)
		bld = node.__class__.bld
		try:
			self.parse_cache = bld.parse_cache
		except AttributeError:
			bld.parse_cache = {}
			self.parse_cache = bld.parse_cache

		self.addlines(node)
		if env['DEFLINES']:
			self.lines = [('define', x) for x in env['DEFLINES']] + self.lines

		while self.lines:
			(kind, line) = self.lines.pop(0)
			if kind == POPFILE:
				self.currentnode_stack.pop()
				continue
			try:
				self.process_line(kind, line)
			except Exception, e:
				if Logs.verbose:
					error("line parsing failed (%s): %s" % (str(e), line))
					traceback.print_exc()

	def process_line(self, token, line):
		ve = Logs.verbose
		if ve: debug('preproc: line is %s - %s state is %s' % (token, line, self.state))
		state = self.state

		# make certain we define the state if we are about to enter in an if block
		if token in ['ifdef', 'ifndef', 'if']:
			state.append(undefined)
		elif token == 'endif':
			state.pop()

		# skip lines when in a dead 'if' branch, wait for the endif
		if not token in ['else', 'elif', 'endif']:
			if skipped in self.state or ignored in self.state:
				return

		if token == 'if':
			ret = eval_macro(tokenize(line), self.defs)
			if ret: state[-1] = accepted
			else: state[-1] = ignored
		elif token == 'ifdef':
			m = re_mac.search(line)
			if m and m.group(0) in self.defs: state[-1] = accepted
			else: state[-1] = ignored
		elif token == 'ifndef':
			m = re_mac.search(line)
			if m and m.group(0) in self.defs: state[-1] = ignored
			else: state[-1] = accepted
		elif token == 'include' or token == 'import':
			(kind, inc) = extract_include(line, self.defs)
			if inc in self.ban_includes: return
			if token == 'import': self.ban_includes.append(inc)
			if ve: debug('preproc: include found %s    (%s) ' % (inc, kind))
			if kind == '"' or not strict_quotes:
				self.tryfind(inc)
		elif token == 'elif':
			if state[-1] == accepted:
				state[-1] = skipped
			elif state[-1] == ignored:
				if eval_macro(tokenize(line), self.defs):
					state[-1] = accepted
		elif token == 'else':
			if state[-1] == accepted: state[-1] = skipped
			elif state[-1] == ignored: state[-1] = accepted
		elif token == 'define':
			m = re_mac.search(line)
			if m:
				name = m.group(0)
				if ve: debug('preproc: define %s   %s' % (name, line))
				self.defs[name] = line
			else:
				raise PreprocError("invalid define line %s" % line)
		elif token == 'undef':
			m = re_mac.search(line)
			if m and m.group(0) in self.defs:
				self.defs.__delitem__(m.group(0))
				#print "undef %s" % name
		elif token == 'pragma':
			if re_pragma_once.search(line.lower()):
				self.ban_includes.append(self.curfile)

def extract_macro(txt):
	t = tokenize(txt)
	if re_fun.search(txt):
		p, name = t[0]

		p, v = t[1]
		if p != OP: raise PreprocError("expected open parenthesis")

		i = 1
		pindex = 0
		params = {}
		prev = '('

		while 1:
			i += 1
			p, v = t[i]

			if prev == '(':
				if p == IDENT:
					params[v] = pindex
					pindex += 1
					prev = p
				elif p == OP and v == ')':
					break
				else:
					raise PreprocError("unexpected token")
			elif prev == IDENT:
				if p == OP and v == ',':
					prev = v
				elif p == OP and v == ')':
					break
				else:
					raise PreprocError("comma or ... expected")
			elif prev == ',':
				if p == IDENT:
					params[v] = pindex
					pindex += 1
					prev = p
				elif p == OP and v == '...':
					raise PreprocError("not implemented")
				else:
					raise PreprocError("comma or ... expected")
			elif prev == '...':
				raise PreprocError("not implemented")
			else:
				raise PreprocError("unexpected else")

		#~ print (name, [params, t[i+1:]])
		return (name, [params, t[i+1:]])
	else:
		(p, v) = t[0]
		return (v, [[], t[1:]])

re_include = re.compile('^\s*(<(?P<a>.*)>|"(?P<b>.*)")')
def extract_include(txt, defs):
	m = re_include.search(txt)
	if m:
		if m.group('a'): return '<', m.group('a')
		if m.group('b'): return '"', m.group('b')

	# perform preprocessing and look at the result, it must match an include
	toks = tokenize(txt)
	reduce_tokens(toks, defs, ['waf_include'])

	if not toks:
		raise PreprocError("could not parse include %s" % txt)

	if len(toks) == 1:
		if toks[0][0] == STR:
			return '"', toks[0][1]
	else:
		if toks[0][1] == '<' and toks[-1][1] == '>':
			return stringize(toks).lstrip('<').rstrip('>')

	raise PreprocError("could not parse include %s" % txt)

def parse_char(txt):
	if not txt: raise PreprocError("attempted to parse a null char")
	if txt[0] != '\\':
		return ord(txt)
	c = txt[1]
	if c == 'x':
		if len(txt) == 4 and txt[3] in string.hexdigits: return int(txt[2:], 16)
		return int(txt[2:], 16)
	elif c.isdigit():
		if c == '0' and len(txt)==2: return 0
		for i in 3, 2, 1:
			if len(txt) > i and txt[1:1+i].isdigit():
				return (1+i, int(txt[1:1+i], 8))
	else:
		try: return chr_esc[c]
		except KeyError: raise PreprocError("could not parse char literal '%s'" % txt)

def tokenize(s):
	ret = []
	for match in re_clexer.finditer(s):
		m = match.group
		for name in tok_types:
			v = m(name)
			if v:
				if name == IDENT:
					try: v = g_optrans[v]; name = OP
					except KeyError:
						# c++ specific
						if v.lower() == "true":
							v = 1
							name = NUM
						elif v.lower() == "false":
							v = 0
							name = NUM
				elif name == NUM:
					if m('oct'): v = int(v, 8)
					elif m('hex'): v = int(m('hex'), 16)
					elif m('n0'): v = m('n0')
					else:
						v = m('char')
						if v: v = parse_char(v)
						else: v = m('n2') or m('n4')
				elif name == OP:
					if v == '%:': v='#'
					elif v == '%:%:': v='##'

				ret.append((name, v.strip('"')))
				break
	return ret

