#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005-2010 (ita)

"""
Node: filesystem structure, contains lists of nodes

1. Each file/folder is represented by exactly one node.

2. Some potential class properties are stored in Build: nodes to depend on..
unused class members increase the .wafpickle file size sensibly with lots of objects.

3. The build is launched from the top of the build dir (for example, in build/).

4. Although Node objects should not be created directly, the methods make_node or find_node may be used for exceptional circumstances

Each instance of Build.BuildContext has a unique Node subclass.
(aka: 'Nod3', see BuildContext initializer)
The BuildContext is referenced here as self.bld
Its Node class is referenced here as self.__class__
"""

import os, shutil, re
import Utils
import Base

# These fnmatch expressions are used by default to prune the directory tree
# while doing the recursive traversal in the find_iter method of the Node class.
prune_pats = '.git .bzr .hg .svn _MTN _darcs CVS SCCS'.split()

# These fnmatch expressions are used by default to exclude files and dirs
# while doing the recursive traversal in the find_iter method of the Node class.
exclude_pats = prune_pats + '*~ #*# .#* %*% ._* .gitignore .cvsignore vssver.scc .DS_Store'.split()

# These Utils.jar_regexp expressions are used by default to exclude files and dirs and also prune the directory tree
# while doing the recursive traversal in the ant_glob method of the Node class.
exclude_regs = '''
**/*~
**/#*#
**/.#*
**/%*%
**/._*
**/CVS
**/CVS/**
**/.cvsignore
**/SCCS
**/SCCS/**
**/vssver.scc
**/.svn
**/.svn/**
**/.git
**/.git/**
**/.gitignore
**/.bzr
**/.bzr/**
**/.hg
**/.hg/**
**/_MTN
**/_MTN/**
**/_darcs
**/_darcs/**
**/.DS_Store'''

class Node(object):
	"""
	This class is divided into two parts, the basic methods meant for filesystem access, and
	the ones which are bound to a context (the build context). The imports do not reflect this.
	"""

	__slots__ = ('name', 'sig', 'children', 'parent', 'cache_abspath', 'cache_isdir')
	def __init__(self, name, parent):
		self.name = name
		self.parent = parent

		if parent:
			if name in parent.children:
				raise Base.WafError('node %s exists in the parent files %r already' % (name, parent))
			parent.children[name] = self

	def __setstate__(self, data):
		self.name = data[0]
		self.parent = data[1]
		if data[2] is not None:
			self.children = data[2]
		if data[3] is not None:
			self.sig = data[3]

	def __getstate__(self):
		return (self.name, self.parent, getattr(self, 'children', None), getattr(self, 'sig', None))

	def __str__(self):
		return self.name

	def __repr__(self):
		return self.abspath()

	def __hash__(self):
		"expensive, make certain it is not used"
		raise Base.WafError('nodes, you are doing it wrong')

	def __eq__(self, node):
		return id(self) == id(node)

	def __copy__(self):
		"nodes are not supposed to be copied"
		raise Base.WafError('nodes are not supposed to be copied')

	def read(self, flags='r'):
		"get the contents, assuming the node is a file"
		return Utils.readf(self.abspath(), flags)

	def write(self, data, flags='w'):
		"write some text to the physical file, assuming the node is a file"
		f = None
		try:
			f = open(self.abspath(), flags)
			f.write(data)
		finally:
			if f:
				f.close()

	def chmod(self, val):
		"change file/dir permissions"
		os.chmod(self.abspath(), val)

	def delete(self):
		"delete the file physically, do not destroy the nodes"
		try:
			shutil.rmtree(self.abspath())
		except:
			pass

		try:
			delattr(self, 'children')
		except:
			pass

	def suffix(self):
		"scons-like - hot zone so do not touch"
		k = max(0, self.name.rfind('.'))
		return self.name[k:]

	def height(self):
		"amount of parents"
		d = self
		val = -1
		while d:
			d = d.parent
			val += 1
		return val

	def compute_sig(self):
		"compute the signature if it is a file"
		try:
			if id(self) in self.bld.hash_cache:
				return
		except AttributeError:
			self.bld.hash_cache = {}

		self.bld.hash_cache[id(self)] = True

		self.sig = Utils.h_file(self.abspath())

	def listdir(self):
		"list the directory contents"
		return Utils.listdir(self.abspath())

	def mkdir(self):
		"write a directory for the node"
		if getattr(self, 'cache_isdir', None):
			return

		try:
			self.parent.mkdir()
		except:
			pass

		if self.name:
			try:
				os.mkdir(self.abspath())
			except OSError as e:
				pass

			if not os.path.isdir(self.abspath()):
				raise Base.WafError('%s is not a directory' % self)

			try:
				self.children
			except:
				self.children = {}

		self.cache_isdir = True

	def find_node(self, lst):
		"read the file system, make the nodes as needed"

		if isinstance(lst, str):
			lst = [x for x in lst.split('/') if x and x != '.']

		cur = self
		for x in lst:
			if x == '..':
				cur = cur.parent
				continue

			try:
				if x in cur.children:
					cur = cur.children[x]
					continue
			except:
				cur.children = {}

			# optimistic: create the node first then look if it was correct to do so
			cur = self.__class__(x, cur)
			try:
				os.stat(cur.abspath())
			except:
				del cur.parent.children[x]
				return None

		ret = cur

		try:
			while not getattr(cur.parent, 'cache_isdir', None):
				cur = cur.parent
				cur.cache_isdir = True
		except AttributeError:
			pass

		return ret

	def make_node(self, lst):
		"make a branch of nodes"
		if isinstance(lst, str):
			lst = [x for x in lst.split('/') if x and x != '.']

		cur = self
		for x in lst:
			if x == '..':
				cur = cur.parent
				continue

			if getattr(cur, 'children', {}):
				if x in cur.children:
					cur = cur.children[x]
					continue
			else:
				cur.children = {}
			cur = self.__class__(x, cur)
		return cur

	def search(self, lst):
		"dumb search for existing nodes"
		if isinstance(lst, str):
			lst = [x for x in lst.split('/') if x and x != '.']

		cur = self
		try:
			for x in lst:
				if x == '..':
					cur = cur.parent
					continue
				cur = cur.children[x]
			return cur
		except:
			pass

	def path_from(self, node):
		"""path of this node seen from the other
			self = foo/bar/xyz.txt
			node = foo/stuff/
			-> ../bar/xyz.txt
		"""
		# common root in rev 7673

		c1 = self
		c2 = node

		c1h = c1.height()
		c2h = c2.height()

		lst = []
		up = 0

		while c1h > c2h:
			lst.append(c1.name)
			c1 = c1.parent
			c1h -= 1

		while c2h > c1h:
			up += 1
			c2 = c2.parent
			c2h -= 1

		while id(c1) != id(c2):
			lst.append(c1.name)
			up += 1

			c1 = c1.parent
			c2 = c2.parent

		for i in range(up):
			lst.append('..')
		lst.reverse()
		return os.sep.join(lst) or '.'

	def abspath(self):
		"""
		absolute path
		cache into the build context, cache_node_abspath
		"""
		try:
			return self.cache_abspath
		except:
			pass
		# think twice before touching this (performance + complexity + correctness)
		if not self.parent:
			val = os.sep == '/' and os.sep or ''
		elif not self.parent.name:
			# drive letter for win32
			val = (os.sep == '/' and os.sep or '') + self.name
		else:
			val = self.parent.abspath() + os.sep + self.name

		self.cache_abspath = val
		return val

	# the following methods require the source/build folders (bld.srcnode/bld.bldnode)

	def is_src(self):
		cur = self
		x = id(self.bld.srcnode)
		y = id(self.bld.bldnode)
		while cur.parent:
			if id(cur) == y:
				return False
			if id(cur) == x:
				return True
			cur = cur.parent
		return False

	def get_src(self):
		cur = self
		x = id(self.bld.srcnode)
		y = id(self.bld.bldnode)
		lst = []
		while cur.parent:
			if id(cur) == y:
				lst.reverse()
				return self.bld.srcnode.make_node(lst)
			if id(cur) == x:
				return self
			lst.append(cur.name)
			cur = cur.parent
		return self

	def get_bld(self):
		cur = self
		x = id(self.bld.srcnode)
		y = id(self.bld.bldnode)
		lst = []
		while cur.parent:
			if id(cur) == y:
				return self
			if id(cur) == x:
				lst.reverse()
				return self.bld.bldnode.make_node(lst)
			lst.append(cur.name)
			cur = cur.parent
		return self

	def is_bld(self):
		cur = self
		y = id(self.bld.bldnode)
		while cur.parent:
			if id(cur) == y:
				return True
			cur = cur.parent
		return False

	def find_resource(self, lst):
		"""
		try to find a declared build node or a source file
		"""
		if isinstance(lst, str):
			lst = [x for x in lst.split('/') if x and x != '.']

		if self.is_bld():
			node = self.search(lst)
			if node:
				return node
			self = self.get_src() # !!!

		node = self.search(lst)
		if node:
			# compute the signature only once
			node.compute_sig()
			return node

		node = self.get_bld().search(lst)
		if node:
			return node

		node = self.find_node(lst)
		if node:
			# compute the signature only once
			node.compute_sig()
			return node

		return node

	def find_or_declare(self, lst):
		"""
		if 'self' is in build directory, try to return an existing node
		if no node is found, go to the source directory
		try to find an existing node in the source directory
		if no node is found, create it in the build directory
		"""
		if isinstance(lst, str):
			lst = [x for x in lst.split('/') if x and x != '.']

		node = self.get_bld().search(lst)
		if node:
			if not os.path.isfile(node.abspath()):
				node.sig = None
				try:
					node.parent.mkdir()
				except:
					pass
			return node
		self = self.get_src()
		node = self.find_node(lst)
		if node:
			if not os.path.isfile(node.abspath()):
				node.sig = None
				try:
					node.parent.mkdir()
				except:
					pass
			return node
		node = self.get_bld().make_node(lst)
		node.parent.mkdir()
		return node

	def find_dir(self, lst):
		"""
		search a folder in the filesystem
		create the corresponding mappings source <-> build directories
		"""
		if isinstance(lst, str):
			lst = [x for x in lst.split('/') if x and x != '.']

		node = self.find_node(lst)
		try:
			os.path.isdir(node.abspath())
		except OSError:
			return None
		return node

	# helpers for building things
	def change_ext(self, ext):
		"node of the same path, but with a different extension - hot zone so do not touch"
		name = self.name
		k = name.rfind('.')
		if k >= 0:
			name = name[:k] + ext
		else:
			name = name + ext

		return self.parent.find_or_declare([name])

	def nice_path(self, env=None):
		"printed in the console, open files easily from the launch directory"
		return self.path_from(self.bld.launch_node())

	def bldpath(self):
		"path seen from the build directory default/src/foo.cpp"
		return self.path_from(self.bld.bldnode)

	def srcpath(self):
		"path seen from the source directory ../src/foo.cpp"
		return self.path_from(self.bld.srcnode)

	def relpath(self):
		"if a build node, bldpath, else srcpath"
		cur = self
		x = id(self.bld.bldnode)
		while cur.parent:
			if id(cur) == x:
				return self.bldpath()
			cur = cur.parent
		return self.srcpath()

	def bld_dir(self):
		"build path without the file name"
		return self.parent.bldpath()

	def bld_base(self):
		"build path without the extension: src/dir/foo(.cpp)"
		s = os.path.splitext(self.name)[0]
		return self.bld_dir() + os.sep + s


	# complicated stuff below

	def ant_glob(self, *k, **kw):

		src=kw.get('src', 1)
		bld=kw.get('bld', 1)
		dir=kw.get('dir', 0)
		excl = kw.get('excl', exclude_regs)
		incl = k and k[0] or kw.get('incl', '**')

		def to_pat(s):
			lst = Utils.to_list(s)
			ret = []
			for x in lst:
				x = x.replace('//', '/')
				if x.endswith('/'):
					x += '**'
				lst2 = x.split('/')
				accu = []
				for k in lst2:
					if k == '**':
						accu.append(k)
					else:
						k = k.replace('.', '[.]').replace('*', '.*').replace('?', '.')
						k = '^%s$' % k
						#print "pattern", k
						accu.append(re.compile(k))
				ret.append(accu)
			return ret

		def filtre(name, nn):
			ret = []
			for lst in nn:
				if not lst:
					pass
				elif lst[0] == '**':
					ret.append(lst)
					if len(lst) > 1:
						if lst[1].match(name):
							ret.append(lst[2:])
					else:
						ret.append([])
				elif lst[0].match(name):
					ret.append(lst[1:])
			return ret

		def accept(name, pats):
			nacc = filtre(name, pats[0])
			nrej = filtre(name, pats[1])
			if [] in nrej:
				nacc = []
			return [nacc, nrej]

		def ant_iter(nodi, maxdepth=25, pats=[]):

			dircont = nodi.listdir()

			try:
				lst = set(nodi.children.keys())
				for x in lst - set(dircont):
					del nodi.children[x]
			except:
				nodi.children = {}

			for name in dircont:

				npats = accept(name, pats)
				if npats and npats[0]:
					accepted = [] in npats[0]
					#print accepted, nodi, name

					node = nodi.make_node([name])
					if accepted:
						yield node

					if getattr(node, 'cache_isdir', None) or os.path.isdir(node.abspath()):
						node.cache_isdir = True
						if maxdepth:
							for k in ant_iter(node, maxdepth=maxdepth - 1, pats=npats):
								yield k
			raise StopIteration

		ret = [x for x in ant_iter(self, pats=[to_pat(incl), to_pat(excl)])]

		if kw.get('flat', True):
			return " ".join([x.path_from(self) for x in ret])

		return ret

class Nod3(Node):
	pass

