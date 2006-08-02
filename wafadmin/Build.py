#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

import os, os.path, sys, cPickle, types
import Environment, Params, Runner, Object, Utils, Node
from Params import debug, error, trace, fatal

g_saved_attrs = 'm_root m_srcnode m_bldnode m_tstamp_variants m_depends_on m_deps_tstamp m_raw_deps'.split()
class BuildDTO:
	def __init__(self):
		pass
	def init(self, bdobj):
		global g_saved_attrs
		for a in g_saved_attrs:
			setattr(self, a, getattr(bdobj, a))
	def update_build(self, bdobj):
		global g_saved_attrs
		for a in g_saved_attrs:
			setattr(bdobj, a, getattr(self, a))

class Build:
	def __init__(self):

		# ======================================= #
		# dependency tree

		self._init_data()

		# ======================================= #
		# globals

		# map a name to an environment, the 'default' must be defined
		self.m_allenvs = {}

		# there should be only one build dir in use at a time
		Params.g_build = self

		# ======================================= #
		# code for reading the scripts

		# project build directory - do not reset() from load_dirs() or _init_data()
		self.m_bdir = ''

		# the current directory from which the code is run
		# the folder changes everytime a wscript is read
		self.m_curdirnode = None

		# temporary holding the subdirectories containing scripts - look in Scripting.py
		self.m_subdirs=[]

		# ======================================= #
		# cache variables

		# local cache for absolute paths - m_abspath_cache[variant][node]
		self.m_abspath_cache = {}

		# local cache for relative paths
		# two nodes - hashtable of hashtables - g_relpath_cache[child][parent])
		self._relpath_cache = {}

		# cache for height of the node (amount of folders from the root)
		self.m_height_cache = {}

		# list of folders that are already scanned
		# so that we do not need to stat them one more time
		self.m_scanned_folders  = []

		# file contents
		self._cache_node_content = {}

		# ======================================= #
		# tasks and objects

		# objects that are not posted and objects already posted
		# -> delay task creation
		self.m_outstanding_objs = []
		self.m_posted_objs      = []

		# build dir variants (release, debug, ..)
		self.set_variants(['default'])

		# TODO used by xmlwaf
		self.pushed = []

	def _init_data(self):
		trace("init data called")

		# filesystem root - root name is Params.g_rootname
		self.m_root            = Node.Node('', None)

		# source directory
		self.m_srcnode         = None
		# build directory
		self.m_bldnode         = None

		# TODO: this code does not look too good
		# nodes signatures: self.m_tstamp_variants[variant_name][node] = signature_value
		self.m_tstamp_variants = {}

		# one node has nodes it depends on, tasks cannot be stored
		# self.m_depends_on[variant][node] = [node1, node2, ..]
		self.m_depends_on      = {}

		# m_deps_tstamp[variant][node] = node_tstamp_of_the_last_scan
		self.m_deps_tstamp     = {}

		# results of a scan: self.m_raw_deps[variant][node] = [filename1, filename2, filename3]
		# for example, find headers in c files
		self.m_raw_deps        = {}

	def _init_variants(self):
		trace("init variants")
		for name in self._variants+[0]:
			for v in 'm_tstamp_variants m_depends_on m_deps_tstamp m_raw_deps m_abspath_cache'.split():
				var = getattr(self, v)
				if not name in var:
					var[name] = {}

	# load existing data structures from the disk (stored using self._store())
	def _load(self):
		try:
			file = open(os.path.join(self.m_bdir, Params.g_dbfile), 'rb')
			dto = cPickle.load(file)
			dto.update_build(self)
			file.close()
		except:
			debug("resetting the build object (dto failed)")
			self._init_data()
			self._init_variants()
		#self.dump()

	# store the data structures on disk, retrieve with self._load()
	def _store(self):
		file = open(os.path.join(self.m_bdir, Params.g_dbfile), 'wb')
		dto = BuildDTO()
		dto.init(self)
		#cPickle.dump(dto, file, -1) # optimized version, do not use in development phase
		cPickle.dump(dto, file)
		file.close()

	# ======================================= #

	def set_variants(self, variants):
		trace("set_variants")
		self._variants = variants
		self._init_variants()

	def save(self):
		self._store()

	# TODO: is this really useful ?
	# usual computation types - dist and distclean might come here too
	def clean(self):
		trace("clean called")

	# keep
	def compile(self):
		trace("compile called")
		ret = 0

		os.chdir(self.m_bdir)


		Object.flush()

		#self.dump()

		if Params.g_maxjobs <=1:
			generator = Runner.JobGenerator(self)
			executor = Runner.Serial(generator)
		else:
			executor = Runner.Parallel(self, Params.g_maxjobs)

		trace("executor starting")
		try:
			ret = executor.start()
		except KeyboardInterrupt:
			os.chdir(self.m_srcnode.abspath())
			self._store()
			raise
		#finally:
		#	os.chdir( self.m_srcnode.abspath() )

		#self.dump()

		os.chdir( self.m_srcnode.abspath() )
		return ret

	# this function is called for both install and uninstall
	def install(self):
		trace("install called")
		Object.flush()
		for obj in Object.g_allobjs: obj.install()

	# keep
	def add_subdirs(self, dirs):
		import Scripting
		if type(dirs) is types.ListType: lst = dirs
		else: lst = dirs.split()

		for d in lst:
			if not d: continue
			Scripting.add_subdir(d, self)

	# keep
	def create_obj(self, objname, *k, **kw):
		try:
			return Object.g_allclasses[objname](*k, **kw)
		except:
			print "error in create_obj", objname
			raise

	# ======================================= #
	# node and folder handling

	# this should be the main entry point
	def load_dirs(self, srcdir, blddir, isconfigure=None):
		# this functions should be the start
		# there is no reason to bypass this check
		try:
			if srcdir == blddir or os.path.samefile(srcdir, blddir):
				fatal("build dir must be different from srcdir ->"+str(srcdir)+" ->"+str(blddir))
		except:
			pass

		# set the source directory
		if srcdir[0] != '/':
			srcdir = os.path.abspath('.') + os.sep + srcdir

		# set the build directory it is a path, not a node (either absolute or relative)
		if blddir[0] != '/':
			self.m_bdir = os.path.abspath(blddir)
		else:
			self.m_bdir = blddir
		#print "self.m_bdir is ", self.m_bdir

		if not isconfigure:
			self._load()
			if self.m_srcnode:
				self.m_curdirnode = self.m_srcnode
				return


		self.m_srcnode = self.ensure_node_from_path(srcdir)
		debug("srcnode is "+str(self.m_srcnode)+" and srcdir "+srcdir)

		self.m_curdirnode = self.m_srcnode

		self.m_bldnode = self.ensure_node_from_path(self.m_bdir)

		# create this build dir if necessary
		try: os.makedirs(blddir)
		except: pass

	# return a node corresponding to an absolute path, creates nodes if necessary
	def ensure_node_from_path(self, abspath):
		trace('ensure_node_from_path %s' % (abspath))
		plst = abspath.split('/')
		curnode = self.m_root # root of the tree
		for dirname in plst:
			if not dirname: continue
			if dirname == '.': continue
			found=None
			for cand in curnode.m_dirs:
				if cand.m_name == dirname:
					found = cand
					break
			if not found:
				found = Node.Node(dirname, curnode)
				curnode.m_dirs.append(found)
			curnode = found

		return curnode

	# ensure a directory node from a list, given a node to start from
	def ensure_node_from_lst(self, node, plst):

		if not node:
			error('ensure_node_from_lst node is not defined')
			raise "pass a valid node to ensure_node_from_lst"

		curnode=node
		for dirname in plst:
			if not dirname: continue
			if dirname == '.': continue
			found=None
			for cand in curnode.m_dirs:
				if cand.m_name == dirname:
					found = cand
					break
			if not found:
				found = Node.Node(dirname, curnode)
				curnode.m_dirs.append(found)
			curnode = found
		return curnode

	def rescan(self, src_dir_node):
		# first list the files in the src dir and update the nodes
		# for each variant build dir (multiple build dirs):
		#     list the files in the build dir, update the nodes
		#
		# this makes (n bdirs)+srdir to scan (at least 2 folders)
		# so we might want to do it in parallel in the future

		# do not rescan over and over again
		if src_dir_node in self.m_scanned_folders: return

		debug("rescanning "+str(src_dir_node))

		# list the files in the src directory, adding the signatures
		files = self._scan_src_path(src_dir_node, src_dir_node.abspath(), src_dir_node.m_files)
		debug("files found in folder are "+str(files))
		src_dir_node.m_files = files

		# list the files in the build dirs
		# remove the existing timestamps if the build files are removed
		lst = self.m_srcnode.difflst(src_dir_node)
		for variant in self._variants:
			sub_path = os.sep.join([self.m_bldnode.abspath(), variant] + lst)
			try:
				files = self._scan_path(src_dir_node, sub_path, src_dir_node.m_build, variant)
				src_dir_node.m_build = files
			except OSError:
				debug("osError on " + sub_path)

				# listdir failed, remove all sigs of nodes
				dict = self.m_tstamp_variants[variant]
				for node in src_dir_node.m_build:
					if node in dict:
						dict.__delitem__(node)
				os.makedirs(sub_path)
				src_dir_node.m_build = []
		self.m_scanned_folders.append(src_dir_node)

	# tell if a node has changed, to update the cache
	def needs_rescan(self, node, env):
		#print "needs_rescan for ", node, node.m_tstamp

		if node in node.m_parent.m_files: variant = 0
		else: variant = env.variant()

		try:
			if self.m_deps_tstamp[variant][node] == self.m_tstamp_variants[variant][node]:
				#print "no need to rescan", node.m_tstamp
				return 0
		except:
			pass
		return 1

	# ======================================= #

	# shortcut for object creation
	def createObj(self, objname, *k, **kw):
		try:
			return Object.g_allclasses[objname](*k, **kw)
		except:
			error("error in createObj "+str(objname))
			raise

	def _scan_src_path(self, i_parent_node, i_path, i_existing_nodes):

		# read the dir contents, ignore the folders in it
		l_names_read = os.listdir(i_path)

		debug("folder contents "+str(l_names_read))

		# there are two ways to obtain the partitions:
		# 1 run the comparisons two times (not very smart)
		# 2 reduce the sizes of the list while looping

		l_names = l_names_read
		l_nodes = i_existing_nodes
		l_kept  = []
	
		for node in l_nodes:
			i     = 0
			name  = node.m_name
			l_len = len(l_names)
			while i < l_len:
				if l_names[i] == name:
					l_kept.append(node)
					break
				i += 1
			if i < l_len:
				del l_names[i]

		# Now:
		# l_names contains the new nodes (or files)
		# l_kept contains only nodes that actually exist on the filesystem
		for node in l_kept:
			try:
				# update the time stamp
				self.m_tstamp_variants[0][node] = Params.h_file(node.abspath())
			except:
				fatal("a file is readonly or has become a dir "+node.abspath())

		debug("new files found "+str(l_names))

		l_path = i_path + os.sep
		for name in l_names:
			try:
				# will throw an exception if not a file or if not readable
				# we assume that this is better than performing a stat() first
				# TODO is it possible to distinguish the cases ?
				st = Params.h_file(l_path + name)
				l_child = Node.Node(name, i_parent_node)
			except:
				continue
			self.m_tstamp_variants[0][l_child] = st
			l_kept.append(l_child)
		return l_kept

	# in this function we do not add timestamps but we remove them
	# when the files no longer exist (file removed in the build dir)
	def _scan_path(self, i_parent_node, i_path, i_existing_nodes, i_variant):

		# read the dir contents, ignore the folders in it
		l_names_read = os.listdir(i_path)

		# there are two ways to obtain the partitions:
		# 1 run the comparisons two times (not very smart)
		# 2 reduce the sizes of the list while looping

		l_names = l_names_read
		l_nodes = i_existing_nodes
		l_rm    = []

		for node in l_nodes:
			i     = 0
			name  = node.m_name
			l_len = len(l_names)
			while i < l_len:
				if l_names[i] == name:
					break
				i += 1
			if i < l_len:
				del l_names[i]
			else:
				l_rm.append(node)

		# remove the stamps of the nodes that no longer exist in the build dir
		for node in l_rm:

			#print "\nremoving the timestamp of ", node, node.m_name
			#print node.m_parent.m_build
			#print l_names_read
			#print l_names

			if node in self.m_tstamp_variants[i_variant]:
				self.m_tstamp_variants[i_variant].__delitem__(node)
		return l_nodes

	## IMPORTANT - for debugging
	def dump(self):
		def printspaces(count):
			if count>0: return printspaces(count-1)+"-"
			return ""
		def recu(node, count):
			accu = printspaces(count)
			accu+= "> "+node.m_name+" (d)\n"
			for child in node.m_files:
				accu+= printspaces(count)
				accu+= '-> '+child.m_name+' '

				for variant in self.m_tstamp_variants:
					#print "variant %s"%variant
					var = self.m_tstamp_variants[variant]
					#print var
					if child in var:
						accu+=' [%s,%s] ' % (str(variant), Params.vsig(var[child]))

				accu+='\n'
				#accu+= ' '+str(child.m_tstamp)+'\n'
				# TODO #if node.m_files[file].m_newstamp != node.m_files[file].m_oldstamp: accu += "\t\t\t(modified)"
				#accu+= node.m_files[file].m_newstamp + "< >" + node.m_files[file].m_oldstamp + "\n"
			for child in node.m_build:
				accu+= printspaces(count)
				accu+= '-> '+child.m_name+' (b) '

				for variant in self.m_tstamp_variants:
					#print "variant %s"%variant
					var = self.m_tstamp_variants[variant]
					#print var
					if child in var:
						accu+=' [%s,%s] ' % (str(variant), Params.vsig(var[child]))

				accu+='\n'
				#accu+= ' '+str(child.m_tstamp)+'\n'
				# TODO #if node.m_files[file].m_newstamp != node.m_files[file].m_oldstamp: accu += "\t\t\t(modified)"
				#accu+= node.m_files[file].m_newstamp + "< >" + node.m_files[file].m_oldstamp + "\n"
			for dir in node.m_dirs: accu += recu(dir, count+1)
			return accu

		Params.pprint('CYAN', recu(self.m_root, 0) )
		Params.pprint('CYAN', 'size is '+str(self.m_root.size()))

		#keys = self.m_name2nodes.keys()
		#for k in keys:
		#	print k, '\t\t', self.m_name2nodes[k]


	def pushdir(self, dir):
		node = self.ensure_node_from_lst(self.m_curdirnode, dir.split('/'))
		self.pushed = [self.m_curdirnode]+self.pushed
		self.m_curdirnode = node

	def popdir(self):
		self.m_curdirnode = self.pushed.pop(0)


