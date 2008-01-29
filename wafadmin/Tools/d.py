#! /usr/bin/env python
# encoding: utf-8
# Carlos Rafael Giani, 2007 (dv)
# Thomas Nagy, 2007 (ita)

import os, sys, re, optparse
import Object, Utils, Action, Params, checks, Configure, Scan
from Params import debug, error

def filter_comments(filename):
	f = open(filename, 'r')
	txt = f.read()
	f.close()
	buf = []

	i = 0
	max = len(txt)
	while i < max:
		c = txt[i]
		# skip a string
		if c == '"':
			i += 1
			c = ''
			while i < max:
				p = c
				c = txt[i]
				i += 1
				if i == max: return buf
				if c == '"':
					cnt = 0
					while i < cnt and i < max:
						#print "cntcnt = ", str(cnt), self.txt[self.i-2-cnt]
						if txt[i-2-cnt] == '\\': cnt+=1
						else: break
					#print "cnt is ", str(cnt)
					if (cnt%2)==0: break
		# skip a char
		elif c == "'":
			i += 1
			if i == max: return buf
			c = txt[i]
			if c == '\\':
				i += 1
				if i == max: return buf
				c = txt[i]
				if c == 'x':
					i += 2 # skip two chars
			i += 1
			if i == max: return buf
			c = txt[i]
			if c != '\'': print "uh-oh, invalid character"

		# skip a comment
		elif c == '/':
			if i == max: break
			c = txt[i+1]
			# eat /+ +/ comments
			if c == '+':
				i += 1
				nesting = 1
				prev = 0
				while i < max:
					c = txt[i]
					if c == '+':
						prev = 1
					elif c == '/':
						if prev:
							nesting -= 1
							if nesting == 0: break
						else:
							if i < max:
								i += 1
								c = txt[i]
								if c == '+':
									nesting += 1
							else:
								return buf
					else:
						prev = 0
					i += 1
			# eat /* */ comments
			elif c == '*':
				i += 1
				while i < max:
					c = txt[i]
					if c == '*':
						prev = 1
					elif c == '/':
						if prev: break
					else:
						prev = 0
					i += 1
			# eat // comments
			elif c == '/':
				i += 1
				c = txt[i]
				while i < max and c != '\n':
					i += 1
		# a valid char, add it to the buffer
		else:
			buf.append(c)
		i += 1
	return buf

class d_parser(object):
	def __init__(self, env, incpaths):
		#self.code = ''
		#self.module = ''
		#self.imports = []

		self.allnames = []

		self.re_module = re.compile("module\s+([^;]+)")
		self.re_import = re.compile("import\s+([^;]+)")
		self.re_import_bindings = re.compile("([^:]+):(.*)")
		self.re_import_alias = re.compile("[^=]+=(.+)")

		self.env = env

		self.m_nodes = []
		self.m_names = []

		self.incpaths = incpaths

	def tryfind(self, filename):
		found = 0
		for n in self.incpaths:
			found = n.find_source(filename.replace('.', '/')+'.d', create=0)
			if found:
				self.m_nodes.append(found)
				self.waiting.append(found)
				break
		if not found:
			if not filename in self.m_names:
				self.m_names.append(filename)

	def get_strings(self, code):
		#self.imports = []
		self.module = ''
		lst = []

		# get the module name (if present)

		mod_name = self.re_module.search(code)
		if mod_name:
			self.module = re.sub('\s+', '', mod_name.group(1)) # strip all whitespaces

		# go through the code, have a look at all import occurrences

		# first, lets look at anything beginning with "import" and ending with ";"
		import_iterator = self.re_import.finditer(code)
		if import_iterator:
			for import_match in import_iterator:
				import_match_str = re.sub('\s+', '', import_match.group(1)) # strip all whitespaces

				# does this end with an import bindings declaration?
				# (import bindings always terminate the list of imports)
				bindings_match = self.re_import_bindings.match(import_match_str)
				if bindings_match:
					import_match_str = bindings_match.group(1)
					# if so, extract the part before the ":" (since the module declaration(s) is/are located there)

				# split the matching string into a bunch of strings, separated by a comma
				matches = import_match_str.split(',')

				for match in matches:
					alias_match = self.re_import_alias.match(match)
					if alias_match:
						# is this an alias declaration? (alias = module name) if so, extract the module name
						match = alias_match.group(1)

					lst.append(match)
		return lst

	def start(self, node):
		self.waiting = [node]
		# while the stack is not empty, add the dependencies
		while self.waiting:
			nd = self.waiting.pop(0)
			self.iter(nd)

	def iter(self, node):
		path = node.abspath(self.env) # obtain the absolute path
		code = "".join(filter_comments(path)) # read the file and filter the comments
		names = self.get_strings(code) # obtain the import strings
		for x in names:
			# optimization
			if x in self.allnames: continue
			self.allnames.append(x)

			# for each name, see if it is like a node or not
			self.tryfind(x)

class d_scanner(Scan.scanner):
	"scanner for d files"
	def __init__(self):
		Scan.scanner.__init__(self)
		self.do_scan = self.scan
		#self.get_signature = self.get_signature_rec

	def scan(self, task, node):
		"look for .d/.di the .d source need"
		debug("_scan_preprocessor(self, node, env, path_lst)", 'ccroot')
		gruik = d_parser(task.env(), task.inc_paths)
		gruik.start(node)

		if Params.g_verbose:
			debug("nodes found for %s: %s %s" % (str(node), str(gruik.m_nodes), str(gruik.m_names)), 'deps')
			#debug("deps found for %s: %s" % (str(node), str(gruik.deps)), 'deps')
		return (gruik.m_nodes, gruik.m_names)

g_d_scanner = d_scanner()
"scanner for d programs"

class dobj(Object.genobj):

	s_default_ext = ['.d', '.di', '.D']
	def __init__(self, type='program'):
		Object.genobj.__init__(self, type)

		self.dflags = {'gdc':'', 'dmd':''}
		self.importpaths = ''
		self.libs = ''
		self.libpaths = ''
		self.uselib = ''
		self.uselib_local = ''
		self.inc_paths = []

	def apply(self):

		global g_d_scanner

		#initialization
		if self.m_type == 'objects':
			type = 'program'
		else:
			type = self.m_type

		env = self.env.copy()
		dpath_st         = env['DPATH_ST']
		lib_st           = env['DLIB_ST']
		libpath_st       = env['DLIBPATH_ST']

		dflags = {'gdc':[], 'dmd':[]}
		importpaths = []
		libpaths = []
		libs = []

		if type == 'staticlib':
			linktask = self.create_task('ar_link_static', env)
		else:
			linktask = self.create_task('d_link', env)


		uselib = self.to_list(self.uselib)
		seen = []
		names = self.to_list(self.uselib_local)
		while names:
			x = names[0]

			# visit dependencies only once
			if x in seen:
				names = names[1:]
				continue

			# object does not exist ?
			y = Object.name_to_obj(x)
			if not y:
				fatal('object not found in uselib_local: obj %s uselib %s' % (self.name, x))
				names = names[1:]
				continue

			# object has ancestors to process first ? update the list of names
			if y.uselib_local:
				added = 0
				lst = y.to_list(y.uselib_local)
				lst.reverse()
				for u in lst:
					if u in seen: continue
					added = 1
					names = [u]+names
				if added: continue # list of names modified, loop

			# safe to process the current object
			if not y.m_posted: y.post()
			seen.append(x)

			if y.m_type == 'shlib':
				libs = libs + [y.target]
			elif y.m_type == 'staticlib':
				libs = libs + [y.target]
			elif y.m_type == 'objects':
				pass
			else:
				error('%s has unknown object type %s, in apply_lib_vars, uselib_local.'
				      % (y.name, y.m_type))

			# add the link path too
			tmp_path = y.path.bldpath(env)
			if not tmp_path in libpaths: libpaths = [tmp_path] + libpaths

			# set the dependency over the link task
			if y.m_linktask is not None:
				linktask.set_run_after(y.m_linktask)
				dep_nodes = getattr(linktask, 'dep_nodes', [])
				dep_nodes += y.m_linktask.m_outputs
				linktask.dep_nodes = dep_nodes

			# add ancestors uselib too
			# TODO potential problems with static libraries ?
			morelibs = y.to_list(y.uselib)
			for v in morelibs:
				if v in uselib: continue
				uselib = [v]+uselib
			names = names[1:]



		# add compiler flags
		for i in uselib:
			if env['DFLAGS_' + i]:
				for dflag in self.to_list(env['DFLAGS_' + i][env['COMPILER_D']]):
					if not dflag in dflags[env['COMPILER_D']]:
						dflags[env['COMPILER_D']] += [dflag]
		dflags[env['COMPILER_D']] = self.to_list(self.dflags[env['COMPILER_D']]) + dflags[env['COMPILER_D']]

		for dflag in dflags[env['COMPILER_D']]:
			if not dflag in env['DFLAGS'][env['COMPILER_D']]:
				env['DFLAGS'][env['COMPILER_D']] += [dflag]

		d_shlib_dflags = env['D_' + type + '_DFLAGS']
		if d_shlib_dflags:
			for dflag in d_shlib_dflags:
				if not dflag in env['DFLAGS'][env['COMPILER_D']]:
					env['DFLAGS'][env['COMPILER_D']] += [dflag]

		env['_DFLAGS'] = env['DFLAGS'][env['COMPILER_D']]


		# add import paths
		for i in uselib:
			if env['DPATH_' + i]:
				for entry in self.to_list(env['DPATH_' + i]):
					if not entry in importpaths:
						importpaths += [entry]
		importpaths = self.to_list(self.importpaths) + importpaths

		# now process the import paths
		for path in importpaths:
			if os.path.isabs(path):
				imppath = path
			else:
				node = self.path.find_source_lst(Utils.split_path(path))
				self.inc_paths.append(node)
				imppath = node.srcpath(env)
			env.append_unique('_DIMPORTFLAGS', dpath_st % imppath)


		# add library paths
		for i in uselib:
			if env['LIBPATH_' + i]:
				for entry in self.to_list(env['LIBPATH_' + i]):
					if not entry in libpaths:
						libpaths += [entry]
		libpaths = self.to_list(self.libpaths) + libpaths

		# now process the library paths
		for path in libpaths:
			env.append_unique('_DLIBDIRFLAGS', libpath_st % path)


		# add libraries
		for i in uselib:
			if env['LIB_' + i]:
				for entry in self.to_list(env['LIB_' + i]):
					if not entry in libs:
						libs += [entry]
		libs = libs + self.to_list(self.libs)

		# now process the libraries
		for lib in libs:
			env.append_unique('_DLIBFLAGS', lib_st % lib)


		# add linker flags
		for i in uselib:
			dlinkflags = env['DLINKFLAGS_' + i]
			if dlinkflags:
				for linkflag in dlinkflags:
					env.append_unique('DLINKFLAGS', linkflag)

		d_shlib_linkflags = env['D_' + type + '_LINKFLAGS']
		if d_shlib_linkflags:
			for linkflag in d_shlib_linkflags:
				env.append_unique('DLINKFLAGS', linkflag)


		# create compile tasks

		compiletasks = []

		obj_ext = env['D_' + type + '_obj_ext'][0]

		find_source_lst = self.path.find_source_lst

		for filename in self.to_list(self.source):
			node = find_source_lst(Utils.split_path(filename))
			base, ext = os.path.splitext(filename)

			if not ext in self.s_default_ext:
				fatal("unknown file " + filename)

			task = self.create_task('d', env)
			task.set_inputs(node)
			task.set_outputs(node.change_ext(obj_ext))
			task.m_scanner = g_d_scanner
			task.inc_paths = self.inc_paths

			compiletasks.append(task)

		# and after the objects, the remaining is the link step
		# link in a lower priority (101) so it runs alone (default is 10)
		global g_prio_link

		outputs = []
		for t in compiletasks: outputs.append(t.m_outputs[0])
		linktask.set_inputs(outputs)
		linktask.set_outputs(self.path.find_build(self.get_target_name()))

		self.m_linktask = linktask

	def get_target_name(self):
		v = self.env

		prefix = v['D_' + self.m_type + '_PREFIX']
		suffix = v['D_' + self.m_type + '_SUFFIX']

		if not prefix: prefix=''
		if not suffix: suffix=''
		return ''.join([prefix, self.target, suffix])

	def install(self):
		pass

def setup(bld):
	d_str = '${D_COMPILER} ${_DFLAGS} ${_DIMPORTFLAGS} ${D_SRC_F}${SRC} ${D_TGT_F}${TGT}'
	link_str = '${D_LINKER} ${DLNK_SRC_F}${SRC} ${DLNK_TGT_F}${TGT} ${DLINKFLAGS} ${_DLIBDIRFLAGS} ${_DLIBFLAGS}'

	Action.simple_action('d', d_str, 'GREEN', 100)
	Action.simple_action('d_link', link_str, color='YELLOW', prio=101)

	Object.register('d', dobj)

def detect(conf):
	return 1

# quick test #
if __name__ == "__main__":
	#Params.g_verbose = 2
	#Params.g_zones = ['preproc']
	#class dum:
	#	def __init__(self):
	#		self.parse_cache_d = {}
	#Params.g_build = dum()

	try: arg = sys.argv[1]
	except IndexError: arg = "file.d"

	print "".join(filter_comments(arg))
	# TODO
	paths = ['.']

	#gruik = filter()
	#gruik.start(arg)

	#code = "".join(gruik.buf)

	#print "we have found the following code"
	#print code

	#print "now parsing"
	#print "-------------------------------------------"
	'''
	parser_ = d_parser()
	parser_.start(arg)

	print "module: %s" % parser_.module
	print "imports: ",
	for imp in parser_.imports:
		print imp + " ",
	print
'''
