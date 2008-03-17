#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2008 (ita)

"""
the c/c++ configuration routines
"""

import os, types, imp, cPickle, sys, shlex, warnings

# see: http://docs.python.org/lib/module-md5.html
try: from hashlib import md5
except ImportError: from md5 import md5

import Action, Params, Environment, Runner, Build, Utils, Object, Configure
from Params import fatal, warning
from Constants import *

def wrap(cls):
	def foo(self):
		x = globals()[cls.__name__](self)
		#print x
		return x
	setattr(Configure.Configure, 'create_'+cls.__name__, foo)

class enumerator_base(object):
	def __init__(self, conf):
		self.conf      = conf
		self.env       = conf.env
		self.define    = ''
		self.mandatory = 0
		self.message   = ''

	def error(self):
		if self.message:
			fatal(self.message)
		else:
			fatal('A mandatory check failed. Make sure all dependencies are ok and can be found.')

	def update_hash(self, md5hash):
		classvars = vars(self)
		for (var, value) in classvars.iteritems():
			# TODO comparing value to env is fast or slow ?
			if callable(var):      continue
			if value == self:      continue
			if value == self.env:  continue
			if value == self.conf: continue
			md5hash.update(str(value))

	def update_env(self, hashtable):
		# skip this if hashtable is only a string
		if not type(hashtable) is types.StringType:
			for name in hashtable.keys():
				self.env.append_value(name, hashtable[name])

	def validate(self):
		pass

	def hash(self):
		m = md5()
		self.update_hash(m)
		return m.digest()

	def run_cache(self, retvalue):
		# interface, do not remove
		pass

	def run(self):
		self.validate()
		if Params.g_cache_global and not Params.g_options.nocache:
			newhash = self.hash()
			try:
				ret = self.conf.m_cache_table[newhash]
			except KeyError:
				pass # go to A1 just below
			else:
				self.run_cache(ret)
				if self.mandatory and not ret: self.error()
				return ret

		# A1 - no cache or new test
		ret = self.run_test()
		if self.mandatory and not ret: self.error()

		if Params.g_cache_global:
			self.conf.m_cache_table[newhash] = ret
		return ret

	# Override this method, not run()!
	def run_test(self):
		return not Configure.TEST_OK

class configurator_base(enumerator_base):
	def __init__(self, conf):
		enumerator_base.__init__(self, conf)
		self.uselib = ''

class program_enumerator(enumerator_base):
	def __init__(self,conf):
		enumerator_base.__init__(self, conf)

		self.name = ''
		self.path = []
		self.var  = None

	def error(self):
		errmsg = 'program %s cannot be found' % self.name
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def run_cache(self, retval):
		self.conf.check_message('program %s (cached)' % self.name, '', retval, option=retval)
		if self.var: self.env[self.var] = retval

	def run_test(self):
		ret = Configure.find_program_impl(self.env, self.name, self.path, self.var)
		self.conf.check_message('program', self.name, ret, ret)
		if self.var: self.env[self.var] = ret
		return ret
wrap(program_enumerator)

class function_enumerator(enumerator_base):
	def __init__(self,conf):
		enumerator_base.__init__(self, conf)

		self.function      = ''
		self.define        = ''

		self.headers       = []
		self.header_code   = ''
		self.custom_code   = ''

		self.include_paths = []
		self.libs          = []
		self.lib_paths     = []

	def error(self):
		errmsg = 'function %s cannot be found' % self.function
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def validate(self):
		if not self.define:
			self.define = self.function.upper()

	def run_cache(self, retval):
		self.conf.check_message('function %s (cached)' % self.function, '', retval, option='')
		if retval:
			self.conf.define(self.define, retval)
		else:
			self.conf.undefine(self.define)

	def run_test(self):
		ret = not Configure.TEST_OK

		oldlibpath = self.env['LIBPATH']
		oldlib = self.env['LIB']

		code = []
		code.append(self.header_code)
		code.append('\n')
		for header in self.headers:
			code.append('#include <%s>\n' % header)

		if self.custom_code:
			code.append('int main(){%s\nreturn 0;}\n' % self.custom_code)
		else:
			code.append('int main(){\nvoid *p;\np=(void*)(%s);\nreturn 0;\n}\n' % self.function)

		self.env['LIB'] = self.libs
		self.env['LIBPATH'] = self.lib_paths

		obj               = check_data()
		obj.code          = "\n".join(code)
		obj.includes      = self.include_paths
		obj.env           = self.env

		ret = int(self.conf.run_check(obj))
		self.conf.check_message('function %s' % self.function, '', ret, option='')

		if ret:
			self.conf.define(self.define, ret)
		else:
			self.conf.undefine(self.define)

		self.env['LIB'] = oldlib
		self.env['LIBPATH'] = oldlibpath

		return ret
wrap(function_enumerator)

class library_enumerator(enumerator_base):
	"find a library in a list of paths"
	def __init__(self, conf):
		enumerator_base.__init__(self, conf)

		self.name = ''
		self.path = []
		self.code = 'int main() {return 0;}\n'
		self.uselib = '' # to set the LIB_NAME and LIBPATH_NAME
		self.nosystem = 0 # do not use standard lib paths
		self.want_message = 1

	def error(self):
		errmsg = 'library %s cannot be found' % self.name
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def run_cache(self, retval):
		if self.want_message:
			self.conf.check_message('library %s (cached)' % self.name, '', retval, option=retval)
		self.update_env(retval)

	def validate(self):
		if not self.path:
			self.path = Configure.g_stdlibpath
		else:
			if not self.nosystem:
				self.path += Configure.g_stdlibpath

	def run_test(self):
		ret = '' # returns a string

		name = self.env['shlib_PATTERN'] % self.name
		ret  = Configure.find_file(name, self.path)

		if not ret:
			for implib_suffix in self.env['shlib_IMPLIB_SUFFIX']:
				name = self.env['shlib_PREFIX'] + self.name + implib_suffix
				ret  = Configure.find_file(name, self.path)
				if ret: break

		if not ret:
			name = self.env['staticlib_PATTERN'] % self.name
			ret  = Configure.find_file(name, self.path)

		if self.want_message:
			self.conf.check_message('library '+self.name, '', ret, option=ret)
		if self.uselib:
			self.env['LIB_'+self.uselib] += [ self.name ]
			self.env['LIBPATH_'+self.uselib] += [ ret ]

		return ret
wrap(library_enumerator)

class header_enumerator(enumerator_base):
	"find a header in a list of paths"
	def __init__(self,conf):
		enumerator_base.__init__(self, conf)

		self.name   = []
		self.path   = []
		self.define = []
		self.nosystem = 0
		self.want_message = 1

	def validate(self):
		if not self.path:
			self.path = Configure.g_stdincpath
		else:
			if not self.nosystem:
				self.path += Configure.g_stdincpath

	def error(self):
		errmsg = 'cannot find %s in %s' % (self.name, str(self.path))
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def run_cache(self, retval):
		if self.want_message:
			self.conf.check_message('header %s (cached)' % self.name, '', retval, option=retval)
		if self.define: self.env[self.define] = retval

	def run_test(self):
		ret = Configure.find_file(self.name, self.path)
		if self.want_message:
			self.conf.check_message('header', self.name, ret, ret)
		if self.define: self.env[self.define] = ret
		return ret
wrap(header_enumerator)

## ENUMERATORS END
###################

###################
## CONFIGURATORS

class cfgtool_configurator(configurator_base):
	def __init__(self,conf):
		configurator_base.__init__(self, conf)

		self.uselib   = ''
		self.define   = ''
		self.binary   = ''

		self.tests    = {}

	def error(self):
		errmsg = '%s cannot be found' % self.binary
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def validate(self):
		if not self.binary:
			raise ValueError, "no binary given in cfgtool!"
		if not self.uselib:
			raise ValueError, "no uselib given in cfgtool!"
		if not self.define and self.uselib:
			self.define = 'HAVE_'+self.uselib

		if not self.tests:
			self.tests['--cflags'] = 'CCFLAGS'
			self.tests['--cflags'] = 'CXXFLAGS'
			self.tests['--libs']   = 'LINKFLAGS'

	def run_cache(self, retval):
		if retval:
			self.update_env(retval)
			self.conf.define(self.define, 1)
		else:
			self.conf.undefine(self.define)
		self.conf.check_message('config-tool %s (cached)' % self.binary, '', retval, option='')

	def run_test(self):
		retval = {}
		found = Configure.TEST_OK

		null='2>/dev/null'
		if sys.platform == "win32": null='2>nul'
		try:
			ret = os.popen('%s %s %s' % (self.binary, self.tests.keys()[0], null)).close()
			if ret: raise ValueError, "error"

			for flag in self.tests:
				var = self.tests[flag] + '_' + self.uselib
				cmd = '%s %s %s' % (self.binary, flag, null)
				retval[var] = [os.popen(cmd).read().strip()]

			self.update_env(retval)
		except ValueError:
			retval = {}
			found = not Configure.TEST_OK

		if found:
			self.conf.define(self.define, found)
		else:
			self.conf.undefine(self.define)
		self.conf.check_message('config-tool ' + self.binary, '', found, option = '')
		return retval
wrap(cfgtool_configurator)

class pkgconfig_configurator(configurator_base):
	""" pkgconfig_configurator is a frontend to pkg-config variables:
	- name: name of the .pc file  (has to be set at least)
	- version: atleast-version to check for
	- path: override the pkgconfig path (PKG_CONFIG_PATH)
	- uselib: name that could be used in tasks with obj.uselib if not set uselib = upper(name)
	- define: name that will be used in config.h if not set define = HAVE_+uselib
	- variables: list of addional variables to be checked for, for example variables='prefix libdir'
	"""
	def __init__(self, conf):
		configurator_base.__init__(self,conf)

		self.name    = '' # name of the .pc file
		self.version = '' # version to check
		self.pkgpath = os.path.join(Params.g_options.prefix, 'lib', 'pkgconfig') # pkg config path
		self.uselib  = '' # can be set automatically
		self.define  = '' # can be set automatically
		self.binary  = '' # name and path for pkg-config

		# You could also check for extra values in a pkg-config file.
		# Use this value to define which values should be checked
		# and defined. Several formats for this value are supported:
		# - string with spaces to separate a list
		# - list of values to check (define name will be upper(uselib"_"value_name))
		# - a list of [value_name, override define_name]
		self.variables = []
		self.defines = {}

	def error(self):
		if self.version:
			errmsg = 'pkg-config cannot find %s >= %s' % (self.name, self.version)
		else:
			errmsg = 'pkg-config cannot find %s' % self.name
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)


	def validate(self):
		if not self.uselib:
			self.uselib = self.name.upper()
		if not self.define:
			self.define = 'HAVE_'+self.uselib

	def run_cache(self, retval):
		if self.version:
			self.conf.check_message('package %s >= %s (cached)' % (self.name, self.version), '', retval, option='')
		else:
			self.conf.check_message('package %s (cached)' % self.name, '', retval, option='')
		if retval:
			self.conf.define(self.define, 1)
		else:
			self.conf.undefine(self.define)
		self.update_env(retval)

	def _setup_pkg_config_path(self):
		pkgpath = self.pkgpath
		if not pkgpath:
			return ""

		if sys.platform == 'win32':
			if hasattr(self, 'pkgpath_win32_setup'):
				return ""
			pkgpath_env=os.getenv('PKG_CONFIG_PATH')

			if pkgpath_env:
				pkgpath_env = pkgpath_env + ';' +pkgpath
			else:
				pkgpath_env = pkgpath

			os.putenv('PKG_CONFIG_PATH',pkgpath_env)
			setattr(self,'pkgpath_win32_setup',True)
			return ""

		pkgpath = 'PKG_CONFIG_PATH=$PKG_CONFIG_PATH:' + pkgpath
		return pkgpath

	def run_test(self):
		pkgpath = self.pkgpath
		pkgbin = self.binary
		uselib = self.uselib

		# check if self.variables is a string with spaces
		# to separate the variables to check for
		# if yes convert variables to a list
		if type(self.variables) is types.StringType:
			self.variables = str(self.variables).split()

		if not pkgbin:
			pkgbin = 'pkg-config'
		pkgpath = self._setup_pkg_config_path()
		pkgcom = '%s %s' % (pkgpath, pkgbin)

		for key, val in self.defines.items():
			pkgcom += ' --define-variable=%s=%s' % (key, val)

		g_defines = self.env['PKG_CONFIG_DEFINES']
		if type(g_defines) is types.DictType:
			for key, val in g_defines.items():
				if self.defines and self.defines.has_key(key):
					continue
				pkgcom += ' --define-variable=%s=%s' % (key, val)

		retval = {}

		try:
			if self.version:
				cmd = "%s --atleast-version=%s \"%s\"" % (pkgcom, self.version, self.name)
				ret = os.popen(cmd).close()
				Params.debug("pkg-config cmd '%s' returned %s" % (cmd, ret))
				self.conf.check_message('package %s >= %s' % (self.name, self.version), '', not ret)
				if ret: raise ValueError, "error"
			else:
				cmd = "%s \"%s\"" % (pkgcom, self.name)
				ret = os.popen(cmd).close()
				Params.debug("pkg-config cmd '%s' returned %s" % (cmd, ret))
				self.conf.check_message('package %s' % (self.name), '', not ret)
				if ret:
					raise ValueError, "error"

			cflags_I = shlex.split(os.popen('%s --cflags-only-I \"%s\"' % (pkgcom, self.name)).read())
			cflags_other = shlex.split(os.popen('%s --cflags-only-other \"%s\"' % (pkgcom, self.name)).read())
			retval['CCFLAGS_'+uselib] = cflags_other
			retval['CXXFLAGS_'+uselib] = cflags_other
			retval['CPPPATH_'+uselib] = []
			for incpath in cflags_I:
				assert incpath[:2] == '-I' or incpath[:2] == '/I'
				retval['CPPPATH_'+uselib].append(incpath[2:]) # strip '-I' or '/I'

			#env['LINKFLAGS_'+uselib] = os.popen('%s --libs %s' % (pkgcom, self.name)).read().strip()
			# Store the library names:
			modlibs = os.popen('%s --libs-only-l \"%s\"' % (pkgcom, self.name)).read().strip().split()
			retval['LIB_'+uselib] = []
			for item in modlibs:
				retval['LIB_'+uselib].append( item[2:] ) #Strip '-l'

			# Store the library paths:
			modpaths = os.popen('%s --libs-only-L \"%s\"' % (pkgcom, self.name)).read().strip().split()
			retval['LIBPATH_'+uselib] = []
			for item in modpaths:
				retval['LIBPATH_'+uselib].append( item[2:] ) #Strip '-l'

			# Store only other:
			modother = os.popen('%s --libs-only-other \"%s\"' % (pkgcom, self.name)).read().strip().split()
			retval['LINKFLAGS_'+uselib] = []
			for item in modother:
				if str(item).endswith(".la"):
					import libtool
					la_config = libtool.libtool_config(item)
					libs_only_L = la_config.get_libs_only_L()
					libs_only_l = la_config.get_libs_only_l()
					for entry in libs_only_l:
						retval['LIB_'+uselib].append( entry[2:] ) #Strip '-l'
					for entry in libs_only_L:
						retval['LIBPATH_'+uselib].append( entry[2:] ) #Strip '-L'
				else:
					retval['LINKFLAGS_'+uselib].append( item ) #do not strip anything

			for variable in self.variables:
				var_defname = ''
				# check if variable is a list
				if (type(variable) is types.ListType):
					# is it a list of [value_name, override define_name] ?
					if len(variable) == 2 and variable[1]:
						# if so use the overrided define_name as var_defname
						var_defname = variable[1]
					# convert variable to a string that name the variable to check for.
					variable = variable[0]

				# if var_defname was not overrided by the list containing the define_name
				if not var_defname:
					var_defname = uselib + '_' + variable.upper()

				retval[var_defname] = os.popen('%s --variable=%s \"%s\"' % (pkgcom, variable, self.name)).read().strip()

			self.conf.define(self.define, 1)
			self.update_env(retval)
		except ValueError:
			retval = {}
			self.conf.undefine(self.define)

		return retval
wrap(pkgconfig_configurator)

class test_configurator(configurator_base):
	def __init__(self, conf):
		configurator_base.__init__(self, conf)
		self.name = ''
		self.code = ''
		self.flags = ''
		self.define = ''
		self.uselib = ''
		self.want_message = 0

	def error(self):
		errmsg = 'test program would not run'
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def run_cache(self, retval):
		if self.want_message:
			self.conf.check_message('custom code (cached)', '', 1, option=retval['result'])

	def validate(self):
		if not self.code:
			fatal('test configurator needs code to compile and run!')

	def run_test(self):
		obj = check_data()
		obj.code = self.code
		obj.env = self.env
		obj.uselib = self.uselib
		obj.flags = self.flags
		obj.execute = 1
		ret = self.conf.run_check(obj)

		if self.want_message:
			if ret: data = ret['result']
			else: data = ''
			self.conf.check_message('custom code', '', ret, option=data)

		return ret
wrap(test_configurator)

class library_configurator(configurator_base):
	def __init__(self,conf):
		configurator_base.__init__(self,conf)

		self.name = ''
		self.path = []
		self.define = ''
		self.uselib = ''

		self.code = 'int main(){return 0;}\n'

	def error(self):
		errmsg = 'library %s cannot be linked' % self.name
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def run_cache(self, retval):
		self.conf.check_message('library %s (cached)' % self.name, '', retval)
		if retval:
			self.update_env(retval)
			self.conf.define(self.define, 1)
		else:
			self.conf.undefine(self.define)

	def validate(self):
		if not self.path:
			self.path = ['/usr/lib/', '/usr/local/lib', '/lib']

		if not self.uselib:
			self.uselib = self.name.upper()
		if not self.define:
			self.define = 'HAVE_'+self.uselib

		if not self.uselib:
			fatal('uselib is not defined')
		if not self.code:
			fatal('library enumerator must have code to compile')

	def run_test(self):
		oldlibpath = self.env['LIBPATH']
		oldlib = self.env['LIB']

		olduselibpath = self.env['LIBPATH_'+self.uselib]
		olduselib = self.env['LIB_'+self.uselib]

		# try the enumerator to find the correct libpath
		test = self.conf.create_library_enumerator()
		test.name = self.name
		test.want_message = 0
		test.path = self.path
		test.env = self.env
		ret = test.run()

		if ret:
			self.env['LIBPATH_'+self.uselib] += [ ret ]

		self.env['LIB_'+self.uselib] += [ self.name ]


		#self.env['LIB'] = self.name
		#self.env['LIBPATH'] = self.lib_paths

		obj         = check_data()
		obj.code    = self.code
		obj.env     = self.env
		obj.uselib  = self.uselib
		obj.libpath = self.path

		ret = int(self.conf.run_check(obj))
		self.conf.check_message('library %s' % self.name, '', ret)

		if ret:
			self.conf.define(self.define, ret)
		else:
			self.conf.undefine(self.define)

		val = {}
		if ret:
			val['LIBPATH_'+self.uselib] = self.env['LIBPATH_'+self.uselib]
			val['LIB_'+self.uselib] = self.env['LIB_'+self.uselib]
			val[self.define] = ret
		else:
			self.env['LIBPATH_'+self.uselib] = olduselibpath
			self.env['LIB_'+self.uselib] = olduselib

		self.env['LIB'] = oldlib
		self.env['LIBPATH'] = oldlibpath

		return val
wrap(library_configurator)

class framework_configurator(configurator_base):
	def __init__(self,conf):
		configurator_base.__init__(self,conf)

		self.name = ''
		self.custom_code = ''
		self.code = 'int main(){return 0;}\n'

		self.define = '' # HAVE_something

		self.path = []
		self.uselib = ''
		self.remove_dot_h = False

	def error(self):
		errmsg = 'framework %s cannot be found via compiler, try pass -F' % self.name
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def validate(self):
		if not self.uselib:
			self.uselib = self.name.upper()
		if not self.define:
			self.define = 'HAVE_'+self.uselib
		if not self.code:
			self.code = "#include <%s>\nint main(){return 0;}\n"
		if not self.uselib:
			self.uselib = self.name.upper()

	def run_cache(self, retval):
		self.conf.check_message('framework %s (cached)' % self.name, '', retval)
		self.update_env(retval)
		if retval:
			self.conf.define(self.define, 1)
		else:
			self.conf.undefine(self.define)

	def run_test(self):
		oldlkflags = []
		oldccflags = []
		oldcxxflags = []

		oldlkflags += self.env['LINKFLAGS']
		oldccflags += self.env['CCFLAGS']
		oldcxxflags += self.env['CXXFLAGS']

		code = []
		if self.remove_dot_h:
			code.append('#include <%s/%s>\n' % (self.name, self.name))
		else:
			code.append('#include <%s/%s.h>\n' % (self.name, self.name))

		code.append('int main(){%s\nreturn 0;}\n' % self.custom_code)

		linkflags = []
		linkflags += ['-framework', self.name]
		linkflags += ['-F%s' % p for p in self.path]
		cflags = ['-F%s' % p for p in self.path]

		myenv = self.env.copy()
		myenv['LINKFLAGS'] += linkflags

		obj        = check_data()
		obj.code   = "\n".join(code)
		obj.env    = myenv
		obj.uselib = self.uselib

		obj.flags += " ".join (cflags)

		ret = int(self.conf.run_check(obj))
		self.conf.check_message('framework %s' % self.name, '', ret, option='')
		if ret:
			self.conf.define(self.define, ret)
		else:
			self.conf.undefine(self.define)

		val = {}
		if ret:
			val["LINKFLAGS_" + self.uselib] = linkflags
			val["CCFLAGS_" + self.uselib] = cflags
			val["CXXFLAGS_" + self.uselib] = cflags
			val[self.define] = ret

		self.env['LINKFLAGS'] = oldlkflags
		self.env['CCFLAGS'] = oldccflags
		self.env['CXXFLAGS'] = oldcxxflags

		self.update_env(val)

		return val
wrap(framework_configurator)

class header_configurator(configurator_base):
	def __init__(self, conf):
		configurator_base.__init__(self,conf)

		self.name = ''
		self.path = []
		self.header_code = ''
		self.custom_code = ''
		self.code = 'int main() {return 0;}\n'

		self.define = '' # HAVE_something

		self.libs = []
		self.lib_paths = []
		self.uselib = ''

	def error(self):
		errmsg = 'header %s cannot be found via compiler' % self.name
		if self.message: errmsg += '\n%s' % self.message
		fatal(errmsg)

	def validate(self):
		# self.names = self.names.split()
		if not self.define:
			if self.name: self.define = 'HAVE_'+ Utils.quote_define_name(self.name)
			elif self.uselib: self.define = 'HAVE_'+self.uselib

		if not self.code:
			self.code = "#include <%s>\nint main(){return 0;}\n"
		if not self.define:
			fatal('no define given')

	def run_cache(self, retvalue):
		self.conf.check_message('header %s (cached)' % self.name, '', retvalue)
		if retvalue:
			self.update_env(retvalue)
			self.conf.define(self.define, 1)
		else:
			self.conf.undefine(self.define)

	def run_test(self):
		ret = {} # not found

		oldlibpath = self.env['LIBPATH']
		oldlib = self.env['LIB']

		# try the enumerator to find the correct includepath
		if self.uselib:
			test = self.conf.create_header_enumerator()
			test.name = self.name
			test.want_message = 0
			test.path = self.path
			test.env = self.env
			ret = test.run()

			if ret:
				self.env['CPPPATH_'+self.uselib] = ret

		code = []
		code.append(self.header_code)
		code.append('\n')
		code.append('#include <%s>\n' % self.name)

		code.append('int main(){%s\nreturn 0;}\n' % self.custom_code)

		self.env['LIB'] = self.libs
		self.env['LIBPATH'] = self.lib_paths

		obj          = check_data()
		obj.code     = "\n".join(code)
		obj.includes = self.path
		obj.env      = self.env
		obj.uselib   = self.uselib

		ret = int(self.conf.run_check(obj))
		self.conf.check_message('header %s' % self.name, '', ret, option='')

		if ret:
			self.conf.define(self.define, ret)
		else:
			self.conf.undefine(self.define)

		self.env['LIB'] = oldlib
		self.env['LIBPATH'] = oldlibpath

		val = {}
		if ret:
			val['CPPPATH_'+self.uselib] = self.env['CPPPATH_'+self.uselib]
			val[self.define] = ret

		if not ret: return {}
		return val
wrap(header_configurator)

class common_include_configurator(header_enumerator):
	"""Looks for a given header. If found, it will be written later by write_config_header()

	Forced include files are headers that are being used by all source files.
	One can include files this way using gcc '-include file.h' or msvc '/fi file.h'.
	The alternative suggested here (common includes) is:
	Make all files include 'config.h', then add these forced-included headers to
	config.h (good for compilers that don't have have this feature and
	for further flexibility).
	"""
	def run_test(self):
		# if a header was found, header_enumerator returns its directory.
		header_dir = header_enumerator.run_test(self)

		if header_dir:
			# if the header was found, add its path to set of forced_include files
			# to be using later in write_config_header()
			header_path = os.path.join(header_dir, self.name)

			# if this header was not stored already, add it to the list of common headers.
			self.env.append_unique(COMMON_INCLUDES, header_path)

		# the return value of all enumerators is checked by enumerator_base.run()
		return header_dir
wrap(common_include_configurator)

# CONFIGURATORS END
####################

class check_data(object):
	def __init__(self):

		self.env           = '' # environment to use

		self.code          = '' # the code to execute

		self.flags         = '' # the flags to give to the compiler

		self.uselib        = '' # uselib
		self.includes      = '' # include paths

		self.function_name = '' # function to check for

		self.lib           = []
		self.libpath       = [] # libpath for linking

		self.define   = '' # define to add if run is successful

		self.header_name   = '' # header name to check for

		self.execute       = 0  # execute the program produced and return its output
		self.options       = '' # command-line options

		self.force_compiler= None
		self.build_type    = 'program'
setattr(Configure, 'check_data', check_data) # warning, attached to the module

def define(self, define, value):
	"""store a single define and its state into an internal list for later
	   writing to a config header file.  Value can only be
	   a string or int; other types not supported.  String
	   values will appear properly quoted in the generated
	   header file."""
	assert define and isinstance(define, str)

	tbl = self.env[DEFINES]
	if not tbl: tbl = {}

	# the user forgot to tell if the value is quoted or not
	if isinstance(value, str):
		tbl[define] = '"%s"' % str(value)
	elif isinstance(value, int):
		tbl[define] = value
	else:
		raise TypeError

	# add later to make reconfiguring faster
	self.env[DEFINES] = tbl
	self.env[define] = value
setattr(Configure.Configure, "define", define)

def undefine(self, define):
	"""store a single define and its state into an internal list
	   for later writing to a config header file"""
	assert define and isinstance(define, str)

	tbl = self.env[DEFINES]
	if not tbl: tbl = {}

	value = UNDEFINED
	tbl[define] = value

	# add later to make reconfiguring faster
	self.env[DEFINES] = tbl
	self.env[define] = value
setattr(Configure.Configure, "undefine", undefine)

def define_cond(self, name, value):
	"""Conditionally define a name.
	Formally equivalent to: if value: define(name, 1) else: undefine(name)"""
	if value:
		self.define(name, 1)
	else:
		self.undefine(name)
setattr(Configure.Configure, "define_cond", define_cond)

def is_defined(self, define):
	defines = self.env[DEFINES]
	if not defines:
		return False
	try:
		value = defines[define]
	except KeyError:
		return False
	else:
		return (value is not UNDEFINED)
setattr(Configure.Configure, "is_defined", is_defined)

def get_define(self, define):
	"get the value of a previously stored define"
	try: return self.env[DEFINES][define]
	except KeyError: return None
setattr(Configure.Configure, "get_define", get_define)

def write_config_header(self, configfile='config.h', env=''):
	"save the defines into a file"
	if configfile == '': configfile = self.configheader

	lst=Utils.split_path(configfile)
	base = lst[:-1]

	if not env: env = self.env
	base = [self.m_blddir, env.variant()]+base
	dir = os.path.join(*base)
	if not os.path.exists(dir):
		os.makedirs(dir)

	dir = os.path.join(dir, lst[-1])

	# remember config files - do not remove them on "waf clean"
	self.env.append_value('waf_config_files', os.path.abspath(dir))

	inclusion_guard_name = '_%s_WAF' % Utils.quote_define_name(configfile)

	dest = open(dir, 'w')
	dest.write('/* Configuration header created by Waf - do not edit */\n')
	dest.write('#ifndef %s\n#define %s\n\n' % (inclusion_guard_name, inclusion_guard_name))

	# yes, this is special
	if not configfile in self.env['dep_files']:
		self.env['dep_files'] += [configfile]
	if not env[DEFINES]: env[DEFINES]={'missing':'"code"'}
	for key, value in env[DEFINES].iteritems():
		if value is None:
			dest.write('#define %s\n' % key)
		elif value is UNDEFINED:
			dest.write('/* #undef %s */\n' % key)
		else:
			dest.write('#define %s %s\n' % (key, value))

	# Adds common-includes to config header. Should come after defines,
	# so they will be defined for the common include files too.
	for include_file in self.env[COMMON_INCLUDES]:
		dest.write('\n#include "%s"' % include_file)

	dest.write('\n#endif /* %s */\n' % (inclusion_guard_name,))
	dest.close()
setattr(Configure.Configure, "write_config_header", write_config_header)

def set_config_header(self, header):
	"set a config header file"
	self.configheader = header
setattr(Configure.Configure, "set_config_header", set_config_header)

def run_check(self, obj):
	"""compile, link and run if necessary
@param obj: data of type check_data
@return: (False if a error during build happens) or ( (True if build ok) or
(a {'result': ''} if execute was set))
"""
	# first make sure the code to execute is defined
	if not obj.code:
		raise ConfigurationError('run_check: no code to process in check')

	# create a small folder for testing
	dir = os.path.join(self.m_blddir, '.wscript-trybuild')

	# if the folder already exists, remove it
	for (root, dirs, filenames) in os.walk(dir):
		for f in list(filenames):
			os.remove(os.path.join(root, f))

	bdir = os.path.join( dir, '_testbuild_')

	if (not obj.force_compiler and Action.g_actions.get('cpp', None)) or obj.force_compiler == "cpp":
		tp = 'cpp'
		test_f_name = 'test.cpp'
	else:
		tp = 'cc'
		test_f_name = 'test.c'

	# FIXME: by default the following lines are called more than once
	#			we have to make sure they get called only once
	if not os.path.exists(dir):
		os.makedirs(dir)

	if not os.path.exists(bdir):
		os.makedirs(bdir)

	if obj.env: env = obj.env
	else: env = self.env.copy()

	dest=open(os.path.join(dir, test_f_name), 'w')
	dest.write(obj.code)
	dest.close()

	# very important
	Utils.reset()

	back=os.path.abspath('.')

	bld = Build.Build()
	bld.m_allenvs.update(self.m_allenvs)
	bld.m_allenvs['default'] = env
	bld._variants=bld.m_allenvs.keys()
	bld.load_dirs(dir, bdir, isconfigure=1)

	os.chdir(dir)

	# not sure yet when to call this:
	#bld.rescan(bld.m_srcnode)

	o = Object.g_allclasses[tp](obj.build_type)
	o.source   = test_f_name
	o.target   = 'testprog'
	o.uselib   = obj.uselib
	o.cppflags = obj.flags
	o.includes = obj.includes

	# compile the program
	self.mute_logging()
	try:
		ret = bld.compile()
	except Build.BuildError:
		ret = 1
	self.restore_logging()

	# keep the name of the program to execute
	if obj.execute:
		lastprog = o.link_task.m_outputs[0].abspath(o.env)

	#if runopts is not None:
	#	ret = os.popen(obj.link_task.m_outputs[0].abspath(obj.env)).read().strip()

	os.chdir(back)
	Utils.reset()

	# if we need to run the program, try to get its result
	if obj.execute:
		if ret: return not ret
		data = os.popen('"%s"' %lastprog).read().strip()
		ret = {'result': data}
		return ret

	return not ret
setattr(Configure.Configure, "run_check", run_check)

# TODO OBSOLETE remove for waf 1.4
def add_define(self, define, value, quote=-1, comment=''):
	fatal("DEPRECATED use conf.define() / conf.undefine() / conf.define_cond() instead")
setattr(Configure.Configure, "add_define", add_define)

def check_features(self, kind='cc'):
	v = self.env
	# check for compiler features: programs, shared and static libraries
	test = Configure.check_data()
	test.code = 'int main() {return 0;}\n'
	test.env = v
	test.execute = 1
	test.force_compiler = kind
	ret = self.run_check(test)
	self.check_message('compiler could create', 'programs', not (ret is False))
	if not ret: self.fatal("no programs")

	lib_obj = Configure.check_data()
	lib_obj.code = "int k = 3;\n"
	lib_obj.env = v
	lib_obj.build_type = "shlib"
	lib_obj.force_compiler = kind
	ret = self.run_check(lib_obj)
	self.check_message('compiler could create', 'shared libs', not (ret is False))
	if not ret: self.fatal("no shared libs")

	lib_obj = Configure.check_data()
	lib_obj.code = "int k = 3;\n"
	lib_obj.env = v
	lib_obj.build_type = "staticlib"
	lib_obj.force_compiler = kind
	ret = self.run_check(lib_obj)
	self.check_message('compiler could create', 'static libs', not (ret is False))
	if not ret: self.fatal("no static libs")
setattr(Configure.Configure, "check_features", check_features)

