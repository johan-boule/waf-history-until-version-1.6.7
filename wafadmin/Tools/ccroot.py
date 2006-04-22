#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

import os, types
import ccroot
import Action, Object, Params, Scan
from Params import debug, error, trace, fatal

# default priority for link tasks
# an even number means link tasks may be parallelized
# an odd number is probably the thing to do
g_prio_link=101

# fake libtool files
fakelibtool_vardeps = ['CXX', 'PREFIX']
def fakelibtool_build(task):
	# Writes a .la file, used by libtool
	dest  = open(task.m_outputs[0].abspath(), 'w')
	sname = task.m_inputs[0].m_name
	dest.write("# Generated by ltmain.sh - GNU libtool 1.5.18 - (pwn3d by BKsys II code name WAF)\n#\n#\n")
	#if len(env['BKSYS_VNUM'])>0:
	#	vnum=env['BKSYS_VNUM']
	#	nums=vnum.split('.')
	#	src=source[0].name
	#	name = src.split('so.')[0] + 'so'
	#	strn = src+" "+name+"."+str(nums[0])+" "+name
	#	dest.write("dlname='%s'\n" % (name+'.'+str(nums[0])) )
	#	dest.write("library_names='%s'\n" % (strn) )
	#else:
	dest.write("dlname='%s'\n" % sname)
	dest.write("library_names='%s %s %s'\n" % (sname, sname, sname) )
	dest.write("old_library=''\ndependency_libs=''\ncurrent=0\n")
	dest.write("age=0\nrevision=0\ninstalled=yes\nshouldnotlink=no\n")
	dest.write("dlopen=''\ndlpreopen=''\n")
	dest.write("libdir='%s/lib'" % task.m_env['PREFIX'])
	dest.close()
	return 0
fakelibtoolact = Action.GenAction('fakelibtool', fakelibtool_vardeps, buildfunc=fakelibtool_build)

# Parent class for programs and libraries in languages c, c++ and moc (Qt)
class ccroot(Object.genobj):
	def __init__(self, type='program'):
		Object.genobj.__init__(self, type)

		self.env = Params.g_build.m_allenvs['default'].copy()
		if not self.env['tools']: fatal('no tool selected')

		self.includes=''

		self.linkflags=''
		self.linkpaths=''

		self.rpaths=''

		self.uselib=''
		self.useliblocal=''

		self.m_linktask=None
		self.m_deps_linktask=[]



		self._incpaths_lst=[]
		self._bld_incpaths_lst=[]

		self.p_shlib_deps_names=[]
		self.p_staticlib_deps_names=[]

		self.p_compiletasks=[]

		# do not forget to set the following variables in a subclass
		self.p_flag_vars = []
		self.p_type_vars = []

		self.m_type_initials = ''

	# subclass me
	def get_valid_types(self):
		fatal('subclass method get_valid_types of ccroot')

	# adding some kind of genericity is tricky
	# subclass this method if it does not suit your needs
	def apply(self):
		trace("apply called for "+self.m_type_initials)
		if not self.m_type in self.get_valid_types(): fatal('Invalid type for object: '+self.m_type_initials)

		self.apply_lib_vars()
		self.apply_type_vars()
		self.apply_obj_vars()
		self.apply_incpaths()

		obj_ext = self.env[self.m_type+'_obj_ext'][0]
		pre = self.m_type_initials

		# get the list of folders to use by the scanners
                # all our objects share the same include paths anyway
                tree = Params.g_build.m_tree
                dir_lst = { 'path_lst' : self._incpaths_lst }

		lst = self.source.split()
		for filename in lst:

			node = self.m_current_path.find_node( filename.split(os.sep) )
			if not node:
				fatal("source not found: "+filename+" in "+str(self.m_current_path))

			base, ext = os.path.splitext(filename)

			fun = None
			try:
				fun = self.env['handlers_'+pre+'obj_'+ext]
				#print "fun is", 'handlers_cppobj_'+ext, fun
			except:
				pass

			if fun:
				fun(self, node)
				continue

			if tree.needs_rescan(node):
				tree.rescan(node, Scan.c_scanner, dir_lst)

			# create the compilation task: cpp or cc
			task = self.create_task(self.m_type_initials, self.env)

			task.m_scanner = Scan.c_scanner
			task.m_scanner_params = dir_lst

			task.m_inputs  = self.file_in(filename)
			task.m_outputs = self.file_in(base+obj_ext)
			self.p_compiletasks.append(task)

		# and after the objects, the remaining is the link step
		# link in a lower priority (101) so it runs alone (default is 10)
		global g_prio_link
		if self.m_type=='staticlib': linktask = self.create_task(pre+'_link_static', self.env, g_prio_link)
		else:                        linktask = self.create_task(pre+'_link', self.env, g_prio_link)
		outputs = []
		for t in self.p_compiletasks: outputs.append(t.m_outputs[0])
		linktask.m_inputs  = outputs 
		linktask.m_outputs = self.file_in(self.get_target_name())

		self.m_linktask = linktask

		if self.m_type != 'program':	
			latask = self.create_task('fakelibtool', self.env, 200)
			latask.m_inputs = linktask.m_outputs
			latask.m_outputs = self.file_in(self.get_target_name('.la'))
			self.m_latask = latask

		self.apply_libdeps()

	def get_target_name(self, ext=None):
		return self.get_library_name(self.target, self.m_type, ext)

	def get_library_name(self, name, type, ext=None):
		prefix = self.env[type+'_PREFIX']
		suffix = self.env[type+'_SUFFIX']

		if ext: suffix = ext
		if not prefix: prefix=''
		if not suffix: suffix=''
		return ''.join([prefix, name, suffix])

	def apply_libdeps(self):
		# for correct dependency handling, we make here one assumption:
		# the objects that create the libraries we depend on -> they have been created already
		# TODO : the lookup may have a cost, caching the names in a hashtable may be a good idea
		# TODO : bad algorithm
		for obj in Object.g_allobjs:
			# if the object we depend on is not posted we will force it right now
			if obj.target in self.p_staticlib_deps_names:
				if not obj.m_posted: obj.post()
				self.m_linktask.m_run_after.append(obj.m_linktask)
			elif obj.target in self.p_shlib_deps_names:
				if not obj.m_posted: obj.post()
				self.m_linktask.m_run_after.append(obj.m_linktask)
		htbl = Params.g_build.m_tree.m_depends_on
		try:
			htbl[self.m_linktask.m_outputs[0]] += self.m_deps_linktask
		except:
			htbl[self.m_linktask.m_outputs[0]] = self.m_deps_linktask

	def apply_incpaths(self):
		inc_lst = self.includes.split()
		lst = self._incpaths_lst

		# add the build directory
		self._incpaths_lst.append( Params.g_build.m_tree.m_bldnode )

		# now process the include paths
		tree = Params.g_build.m_tree
		for dir in inc_lst:
			node = self.m_current_path.find_node( dir.split(os.sep) )
			if not node:
				error("node not found dammit")
				continue
			lst.append( node )

			node2 = tree.get_mirror_node(node)
			lst.append( node2 )
			if Params.g_mode == 'nocopy':
				lst.append( node )
				self._bld_incpaths_lst.append(node)
			self._bld_incpaths_lst.append(node2)
			
		# now the nodes are added to self._incpaths_lst


	def apply_type_vars(self):
		trace('apply_type_vars called')
		for var in self.p_type_vars:
			# each compiler defines variables like 'shlib_CXXFLAGS', 'shlib_LINKFLAGS', etc
			# so when we make a cppobj of the type shlib, CXXFLAGS are modified accordingly
			compvar = '_'.join([self.m_type, var])
			#print compvar
			value = self.env[compvar]
			if value: self.env.appendValue(var, value)

	def apply_obj_vars(self):
		trace('apply_obj_vars called for cppobj')
		cpppath_st       = self.env['CPPPATH_ST']
		lib_st           = self.env['LIB_ST']
		staticlib_st     = self.env['STATICLIB_ST']
		libpath_st       = self.env['LIBPATH_ST']
		staticlibpath_st = self.env['STATICLIBPATH_ST']

		# local flags come first
		# set the user-defined includes paths
		if not self._incpaths_lst: self.apply_incpaths()
		for i in self._bld_incpaths_lst:
			self.env.appendValue('_CXXINCFLAGS', cpppath_st % i.bldpath())

		# set the library include paths
		for i in self.env['CPPPATH']:
			self.env.appendValue('_CXXINCFLAGS', cpppath_st % i)
			#print self.env['_CXXINCFLAGS']
			#print " appending include ",i
	
		# this is usually a good idea
		self.env.appendValue('_CXXINCFLAGS', cpppath_st % '.')
		try:
			tmpnode = Params.g_build.m_curdirnode
			tmpnode_mirror = Params.g_build.m_tree.self.m_src_to_bld[tmpnode]
			self.env.appendValue('_CXXINCFLAGS', cpppath_st % tmpnode.bldpath())
			self.env.appendValue('_CXXINCFLAGS', cpppath_st % tmpnode_mirror.bldpath())
		except:
			pass

		for i in self.env['RPATH']:
			self.env.appendValue('LINKFLAGS', i)

		for i in self.env['LIBPATH']:
			self.env.appendValue('LINKFLAGS', libpath_st % i)

		for i in self.env['LIBPATH']:
			self.env.appendValue('LINKFLAGS', staticlibpath_st % i)

		if self.env['STATICLIB']:
			self.env.appendValue('LINKFLAGS', self.env['STATICLIB_MARKER'])
			for i in self.env['STATICLIB']:
				self.env.appendValue('LINKFLAGS', staticlib_st % i)

		if self.env['LIB']:
			self.env.appendValue('LINKFLAGS', self.env['SHLIB_MARKER'])
			for i in self.env['LIB']:
				self.env.appendValue('LINKFLAGS', lib_st % i)



	def apply_lib_vars(self):
		trace("apply_lib_vars called")

		# TODO complicated lookups, there are certainly ways to make it simple
		# TODO bad scheme, we are not certain that the node to depend on exists in the first place
		# well, at least we will throw an error message that makes sense
		libs = self.useliblocal.split()

		# store for use when calling "apply"
		sh_names     = self.p_shlib_deps_names
		static_names = self.p_staticlib_deps_names
		tree = Params.g_build.m_tree
		for lib in libs:
			idx=len(lib)-1
			while 1:
				idx = idx - 1
				if lib[idx] == '/': break
			# find the path for linking and the library name
			path = lib[:idx]
			name = lib[idx+1:]
			lst = name.split('.')
			name = lst[0]
			ext = lst[1]

			trace('library found %s %s %s '%(str(name), str(path), str(ext)))
			if ext == 'a':
				type='staticlib'
				static_names.append(name)
			else:
				type='shlib'
				sh_names.append(name)

			# now that the name was added, find the corresponding node in the builddir
			dirnode = self.m_current_path.find_node( path.split('/') )
			self.env.appendValue('LIBPATH', dirnode.srcpath())
			
			# useful for the link path, but also for setting the dependency:
			try:
				dirnode = tree.get_mirror_node(dirnode)
				rname = self.get_library_name(name, type)
				node = dirnode.find_node([rname])
				self.m_deps_linktask.append(node)
			except:
				print "dependency set on a node which does not exist!"
				print "", rname, " in ", dirnode
				print ""
				raise

		self.env.appendValue('LIB', sh_names)
		self.env.appendValue('STATICLIB', static_names)

		libs = self.uselib.split()
		for l in libs:
			for v in self.p_flag_vars:
				val=''
				try:    val = self.env[v+'_'+l]
				except: pass
				if val:
					self.env.appendValue(v, val)


