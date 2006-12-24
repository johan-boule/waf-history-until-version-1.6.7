#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

"""
Node: filesystem structure, contains lists of nodes
self.m_dirs  : sub-folders
self.m_files : files existing in the src dir
self.m_build : nodes produced in the build dirs

A folder is represented by exactly one node

IMPORTANT:
Some would-be class properties are stored in Build: nodes to depend on, signature, flags, ..
In fact, unused class members increase the .wafpickle file size sensibly with lots of objects
eg: the m_tstamp is used for every node, while the signature is computed only for build files

the build is launched from the top of the build dir (for example, in _build_/)
"""

import os
import Params, Utils
from Params import debug, error, fatal

g_launch_node=None

class Node:
	def __init__(self, name, parent):
		self.m_name = name
		self.m_parent = parent
		self.m_cached_path = ""

		# Lookup dictionaries for O(1) access
		self.m_dirs_lookup = {}
		self.m_files_lookup = {}
		self.m_build_lookup = {}

		# The checks below could be disabled for speed, if necessary
		# TODO check for . .. / \ in name

		# Node name must contain only one level
		if Utils.split_path(name)[0] != name:
			fatal('name forbidden '+name)

		if parent:
			if parent.get_file(name):
				fatal('node %s exists in the parent files %s already' % (name, str(parent)))

			if parent.get_build(name):
				fatal('node %s exists in the parent build %s already' % (name, str(parent)))

	def dirs(self):
		return self.m_dirs_lookup.values()

	def get_dir(self,name,default=None):
		return self.m_dirs_lookup.get(name,default)

	def append_dir(self, dir):
		self.m_dirs_lookup[dir.m_name]=dir

	def files(self):
		return self.m_files_lookup.values()

	def set_files(self,files):
		self.m_files_lookup={}
		for i in files: self.m_files_lookup[i.m_name]=i

	def get_file(self,name,default=None):
		return self.m_files_lookup.get(name,default)

	def append_file(self, dir):
		self.m_files_lookup[dir.m_name]=dir

	def set_build(self, build):
		self.m_build_lookup={}
		for i in build: self.m_build_lookup[i.m_name]=i

	def get_build(self,name,default=None):
		return self.m_build_lookup.get(name,default)

	def __str__(self):
		if self.m_name in self.m_parent.m_files_lookup: isbld = ""
		else: isbld = "b:"
		return "<%s%s>" % (isbld, self.abspath())

	def __repr__(self):
		if self.m_name in self.m_parent.m_files_lookup: isbld = ""
		else: isbld = "b:"
		return "<%s%s>" % (isbld, self.abspath())

	# ====================================================== #

	# for the build variants, the same nodes are used to spare memory
	# the timestamps/signatures are accessed using the following methods

	def get_tstamp_variant(self, variant):
		vars = Params.g_build.m_tstamp_variants[variant]
		try: return vars[variant]
		except: return None

	def set_tstamp_variant(self, variant, value):
		Params.g_build.m_tstamp_variants[variant][self] = value

	def get_tstamp_node(self):
		try: return Params.g_build.m_tstamp_variants[0][self]
		except: return None

	def set_tstamp_node(self, value):
		Params.g_build.m_tstamp_variants[0][self] = value

	# ====================================================== #

	# size of the subtree
	def size(self):
		l_size=1
		for i in self.dirs(): l_size += i.size()
		l_size += len(self.files())
		return l_size

	def height(self):
		# TODO enable a cache ?
		d = self
		val = 0
		while d.m_parent:
			d=d.m_parent
			val += 1
		return val

	def child_of_name(self, name):
		return self.get_dir(name,None)
		#for d in self.m_dirs:
		#	debug('child of name '+d.m_name, 300)
		#	if d.m_name == name:
		#		return d
		# throw an exception ?
		#return None

	## ===== BEGIN relpath-related methods	===== ##

	# list of file names that separate a node from a child
	def difflst(self, child):
		if not child: error('Node difflst takes a non-null parameter!')
		lst=[]
		node = child
		while child != self:
			lst.append(child.m_name)
			child=child.m_parent
		lst.reverse()
		return lst

	## ------------ TODO : the following may need to be improved
	# returns a joined path string that can be reduced to the absolute path
	# DOES NOT needs to be reversed anymore (used by abspath)
	def __pathstr2(self):
		if self.m_cached_path: return self.m_cached_path
		dirlist = [self.m_name]
		cur_dir=self.m_parent
		while cur_dir:
			if cur_dir.m_name:
				dirlist = dirlist + [cur_dir.m_name]
			cur_dir = cur_dir.m_parent
		dirlist.reverse()

		joined = ""
		for f in dirlist: joined = os.path.join(joined,f)
		if not os.path.isabs(joined):
			joined = os.sep + joined

		self.m_cached_path=joined
		return joined
		#if not self.m_parent: return [Params.g_rootname]
		#return [self.m_name, os.sep]+self.m_parent.pathlist2()

	def find_node_by_name(self, name, lst):
		res = self.get_dir(name,None)
		if not res:
			res=self.get_file(name)
		if not res:
			res=self.get_build(name)
		if not res: return None

		return res.find_node( lst[1:] )

	# TODO : make it procedural, not recursive
	# find a node given an existing node and a list like ['usr', 'local', 'bin']
	def find_node(self, lst):
		return self.find_node_lst(lst)

	def find_node_lst(self, lst):
		if not lst: return self
		name=lst[0]

		# unfortunately, it is necessary to check if the nodes still exist
		Params.g_build.rescan(self)

		if name == '.':  return self.find_node_lst(lst[1:])
		if name == '..': return self.m_parent.find_node_lst(lst[1:])

		res = self.find_node_by_name(name,lst)
		if res: return res

		if len(lst)>0:
			node = Node(name, self)
			self.append_dir(node)
			#self.m_dirs.append(node)
			return node.find_node_lst(lst[1:])

		#debug('find_node returns nothing '+str(self)+' '+str(lst), 300)
		return None



	def find_or_create(self, path):
		"convenience method"
		lst = Utils.split_path(path)
		return self.find_or_create_lst(lst)

	def find_or_create_lst(self, lst):
		"search for a node, it is created if it does not exist (not recursive)"
		node = self
		for name in lst:
			if name == '.': continue
			if name == '..':
				node = self.m_parent
				continue
			old = node
			node = old.get_file(name)
			if node: continue
			node = old.get_build(name)
			if node: continue
			node = old.get_dir(name)
			if node: continue
			node = Node(name, old)
			old.m_build_lookup[node.m_name]=node
		return node

	def search_existing_node(self, path):
		"convenience method"
		lst = Utils.split_path(path)
		return self.search_existing_node_lst(lst)

	def search_existing_node_lst(self, lst):
		"returns a node from the tree, do not create if missing (not recursive)"
		if not lst: return self
		node = self
		rescan = Params.g_build.rescan
		for name in lst:
			if not node: return None
			rescan(node)
			if name == '.': continue
			if name == '..':
				node = self.m_parent
				continue
			old = node
			node = old.get_file(name)
			if node: continue
			node = old.get_build(name)
			if node: continue
			node = old.get_dir(name)
		return node

	# absolute path
	def abspath(self, env=None):
		variant = self.variant(env)
		try:
			return Params.g_build.m_abspath_cache[variant][self]
		except KeyError:
			if not variant:
				val=self.__pathstr2()
				#lst.reverse() - no need to reverse list anymore
				#val=''.join(lst)
				Params.g_build.m_abspath_cache[variant][self]=val
				return val
			else:
				p = Utils.join_path(Params.g_build.m_bldnode.abspath(),env.variant(),
					self.relpath(Params.g_build.m_srcnode))
				debug("var is p+q is "+p, 'node')
				return p

	def bldpath(self, env=None):
		name = self.m_name
		x = self.m_parent.get_file(name)
		if x: return self.relpath_gen(Params.g_build.m_bldnode)
		return Utils.join_path(env.variant(),self.relpath(Params.g_build.m_srcnode))

	def srcpath(self, env):
		name = self.m_name
		x = self.m_parent.get_build(name)
		if x: return self.bldpath(env)
		return self.relpath_gen(Params.g_build.m_bldnode)

	def bld_dir(self, env):
		return self.m_parent.bldpath(env)

	def bldbase(self, env):
		i = 0
		n = self.m_name
		while 1:
			try:
				if n[i]=='.': break
			except:
				break
			i += 1
		s = n[:i]
		return Utils.join_path(self.bld_dir(env),s)








	# returns the list of names to the node
	# make sure to reverse it (used by relpath)
	def pathlist3(self, node):
		if self is node: return ['.']
		return [self.m_name, os.sep]+self.m_parent.pathlist3(node)

	# same as pathlist3, but do not append './' at the beginning
	def pathlist4(self, node):
		if self.m_parent is node: return [self.m_name]
		return [self.m_name, os.sep]+self.m_parent.pathlist4(node)

	# path relative to a direct parent
	def relpath(self, parent):
		#print "relpath", self, parent
		#try:
		#	return Params.g_build.m_relpath_cache[self][parent]
		#except:
		#	lst=self.pathlist3(parent)
		#	lst.reverse()
		#	val=''.join(lst)

		#	try:
		#		Params.g_build.m_relpath_cache[self][parent]=val
		#	except:
		#		Params.g_build.m_relpath_cache[self]={}
		#		Params.g_build.m_relpath_cache[self][parent]=val
		#	return val
		if self is parent: return ''

		lst=self.pathlist4(parent)
		lst.reverse()
		val=''.join(lst)
		return val


	# find a common ancestor for two nodes - for the shortest path in hierarchy
	def find_ancestor(self, node):
		dist=self.height()-node.height()
		if dist<0: return node.find_ancestor(self)
		# now the real code
		cand=self
		while dist>0:
			cand=cand.m_parent
			dist=dist-1
		if cand is node: return cand
		cursor=node
		while cand.m_parent:
			cand   = cand.m_parent
			cursor = cursor.m_parent
			if cand is cursor: return cand

	# prints the amount of "../" between two nodes
	def invrelpath(self, parent):
		lst=[]
		cand=self
		while cand is not parent:
			cand=cand.m_parent
			lst+=['..',os.sep] #TODO: fix this
		return lst

	# TODO: do this in a single function (this one uses invrelpath, find_ancestor and pathlist4)
	# string representing a relative path between two nodes, we are at relative_to
	def relpath_gen(self, going_to):
		if self is going_to: return '.'
		if going_to.m_parent is self: return '..'

		# up_path is '../../../' and down_path is 'dir/subdir/subdir/file'
		ancestor  = self.find_ancestor(going_to)
		up_path   = going_to.invrelpath(ancestor)
		down_path = self.pathlist4(ancestor)
		down_path.reverse()
		return "".join( up_path+down_path )

	# TODO look at relpath_gen - it is certainly possible to get rid of find_ancestor
	def relpath_gen2(self, going_to):
		if self is going_to: return '.'
		ancestor = Params.srcnode()
		up_path   = going_to.invrelpath(ancestor)
		down_path = self.pathlist4(ancestor)
		down_path.reverse()
		return "".join( up_path+down_path )







	def nice_path(self, env=None):
		"printed in the console, open files easily from the launch directory"
		tree = Params.g_build
		global g_launch_node
		if not g_launch_node:
			g_launch_node = tree.m_root.find_or_create(Params.g_cwd_launch)

		name = self.m_name
		x = self.m_parent.get_file(name)
		if x: return self.relative_path(g_launch_node)
		else: return tree.m_bldnode.relative_path(g_launch_node) + os.sep + self.relative_path(tree.m_srcnode)

	def relative_path(self, folder):
		"relative path between a node and a directory"
		hh1 = h1 = self.height()
		hh2 = h2 = folder.height()
		p1=self
		p2=folder
		while h1>h2:
			p1=p1.m_parent
			h1-=1
		while h2>h1:
			p2=p2.m_parent
			h2-=1

		# now we have two nodes of the same height
		ancestor = None
		if p1.m_name == p2.m_name:
			ancestor = p1
		while p1.m_parent:
			p1=p1.m_parent
			p2=p2.m_parent
			if p1.m_name != p2.m_name:
				ancestor = None
			elif not ancestor:
				ancestor = p1

		anh = ancestor.height()
		n1 = hh1-anh
		n2 = hh2-anh

		lst=[]
		tmp = self
		while n1:
			n1 -= 1
			lst.append(tmp.m_name)
			tmp = tmp.m_parent

		lst.reverse()
		up_path=os.sep.join(lst)
		down_path = (".."+os.sep) * n2

		return "".join( down_path+up_path )

	## ===== END relpath-related methods  ===== ##

	def debug(self):
		print "========= debug node ============="
		print "dirs are ", self.dirs()
		print "files are", self.files()
		print "======= end debug node ==========="

	def is_child_of(self, node):
		p=self
		h1=self.height()
		h2=node.height()
		diff=h1-h2
		while diff>0:
			diff-=1
			p=p.m_parent
		return p.equals(node)

	def equals(self, node):
		p1 = self
		p2 = node
		while p1 and p2:
			if p1.m_name != p2.m_name:
				return 0
			p1=p1.m_parent
			p2=p2.m_parent
		if p1 or p2: return 0
		return 1

	def variant(self, env):
		if not env: return 0
		i = self.m_parent.get_file(self.m_name)
		if i: return 0
		return env.variant()





	#def ensure_scan(self):
	#	if not self in Params.g_build.m_scanned_folders:
	#		Params.g_build.rescan(self)
	#		Params.g_build.m_scanned_folders.append(self)

	# =============================================== #
	# helpers for building things
	def change_ext(self, ext):
		name = self.m_name
		newname = os.path.splitext(name)[0] + ext

		n = self.m_parent.get_file(newname)
		if not n: n = self.m_parent.get_build(newname)
		if n: return n

		newnode = Node(newname, self.m_parent)
		self.m_parent.m_build_lookup[newnode.m_name]=newnode

		return newnode

