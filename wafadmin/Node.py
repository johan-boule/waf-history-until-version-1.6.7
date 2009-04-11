#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

"""
Node: filesystem structure, contains lists of nodes

IMPORTANT:
1. Each file/folder is represented by exactly one node

2. Most would-be class properties are stored in Build: nodes to depend on, signature, flags, ..
unused class members increase the .wafpickle file size sensibly with lots of objects

3. The build is launched from the top of the build dir (for example, in _build_/)

4. Node should not be instantiated directly.
Each instance of Build.BuildContext has a Node sublass.
(aka: 'Nodu', see BuildContext initializer)
The BuildContext is referenced here as self.__class__.bld
Its Node class is referenced here as self.__class__

The public and advertised apis are the following:
${TGT}                 -> dir/to/file.ext
${TGT[0].base()}       -> dir/to/file
${TGT[0].dir(env)}     -> dir/to
${TGT[0].file()}       -> file.ext
${TGT[0].file_base()}   -> file
${TGT[0].suffix()}     -> .ext
${TGT[0].abspath(env)} -> /path/to/dir/to/file.ext

"""

import os, sys, fnmatch, re
import Utils

UNDEFINED = 0
DIR = 1
FILE = 2
BUILD = 3

type_to_string = {UNDEFINED: "unk", DIR: "dir", FILE: "src", BUILD: "bld"}

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
**/.DS_Store'''.split()

exc_fun = None
def default_excludes():
	global exc_fun
	if exc_fun:
		return exc_fun

	regs = [Utils.jar_regexp(x) for x in exclude_regs]
	def mat(path):
		for x in regs:
			if x.match(path):
				return True
		return False

	exc_fun = mat
	return exc_fun

class Node(object):
	__slots__ = ("name", "parent", "id", "childs")
	def __init__(self, name, parent, node_type = UNDEFINED):
		self.name = name
		self.parent = parent

		# assumption: one build object at a time
		self.__class__.bld.id_nodes += 4
		self.id = self.__class__.bld.id_nodes + node_type

		if node_type == DIR: self.childs = {}

		# We do not want to add another type attribute (memory)
		# use the id to find out: type = id & 3
		# for setting: new type = type + x - type & 3

		# Node name must contain only one level
		if Utils.split_path(name)[0] != name:
			raise Utils.WafError('name %r forbidden ' % name)

		if parent and name in parent.childs:
			raise Utils.WafError('node %s exists in the parent files %r already' % (name, parent))

		if parent: parent.childs[name] = self

	def __setstate__(self, data):
		if len(data) == 4:
			(self.parent, self.name, self.id, self.childs) = data
		else:
			(self.parent, self.name, self.id) = data

	def __getstate__(self):
		if getattr(self, 'childs', None) is None:
			return (self.parent, self.name, self.id)
		else:
			return (self.parent, self.name, self.id, self.childs)

	def __str__(self):
		if not self.parent: return ''
		return "%s://%s" % (type_to_string[self.id & 3], self.abspath())

	def __repr__(self):
		return self.__str__()

	def __hash__(self):
		"expensive, make certain it is not used"
		raise Utils.WafError('nodes, you are doing it wrong')

	def __copy__(self):
		"nodes are not supposed to be copied"
		raise Utils.WafError('nodes are not supposed to be cloned')

	def get_type(self):
		return self.id & 3

	def set_type(self, t):
		self.id = self.id + t - self.id & 3

	def dirs(self):
		return [x for x in self.childs.values() if x.id & 3 == DIR]

	def files(self):
		return [x for x in self.childs.values() if x.id & 3 == FILE]

	def get_dir(self, name, default=None):
		node = self.childs.get(name, None)
		if not node or node.id & 3 != DIR: return default
		return  node

	def get_file(self, name, default=None):
		node = self.childs.get(name, None)
		if not node or node.id & 3 != FILE: return default
		return node

	def get_build(self, name, default=None):
		node = self.childs.get(name, None)
		if not node or node.id & 3 != BUILD: return default
		return node

	def find_resource(self, lst):
		"Find an existing input file: either a build node declared previously or a source node"
		if isinstance(lst, str):
			lst = Utils.split_path(lst)

		if len(lst) == 1:
			parent = self
		else:
			parent = self.find_dir(lst[:-1])
			if not parent: return None
		self.__class__.bld.rescan(parent)

		name = lst[-1]
		node = parent.childs.get(name, None)
		if node:
			tp = node.id & 3
			if tp == FILE or tp == BUILD:
				return node
			else:
				return None

		tree = self.__class__.bld
		if not name in tree.cache_dir_contents[parent.id]:
			return None

		path = parent.abspath() + os.sep + name
		try:
			st = Utils.h_file(path)
		except IOError:
			return None

		child = self.__class__(name, parent, FILE)
		tree.node_sigs[0][child.id] = st
		return child

	def find_or_declare(self, lst):
		"Used for declaring a build node representing a file being built"
		if isinstance(lst, str):
			lst = Utils.split_path(lst)

		if len(lst) == 1:
			parent = self
		else:
			parent = self.find_dir(lst[:-1])
			if not parent: return None
		self.__class__.bld.rescan(parent)

		name = lst[-1]
		node = parent.childs.get(name, None)
		if node:
			tp = node.id & 3
			if tp != BUILD:
				raise Utils.WafError("find_or_declare returns a build node, not a source nor a directory %r" % lst)
			return node
		node = self.__class__(name, parent, BUILD)
		return node

	def find_dir(self, lst):
		"search a folder in the filesystem"

		if isinstance(lst, str):
			lst = Utils.split_path(lst)

		current = self
		for name in lst:
			self.__class__.bld.rescan(current)
			prev = current

			if not current.parent and name == current.name:
				continue
			elif not name:
				continue
			elif name == '.':
				continue
			elif name == '..':
				current = current.parent or current
			else:
				current = prev.childs.get(name, None)
				if current is None:
					dir_cont = self.__class__.bld.cache_dir_contents
					# we use rescan above, so dir_cont[prev.id *is* defined]
					if name in dir_cont[prev.id]:
						if not os.path.isdir(prev.abspath() + os.sep + name):
							# paranoid os.stat
							return None
						current = self.__class__(name, prev, DIR)
					else:
						return None
				else:
					if current.id & 3 != DIR:
						return None
		return current

	# FIXME: remove in waf 1.6
	def ensure_dir_node_from_path(self, lst):
		"used very rarely, force the construction of a branch of node instance for representing folders"

		if isinstance(lst, str):
			lst = Utils.split_path(lst)

		current = self
		for name in lst:
			if not name:
				continue
			elif name == '.':
				continue
			elif name == '..':
				current = current.parent or current
			else:
				prev = current
				current = prev.childs.get(name, None)
				if current is None:
					current = self.__class__(name, prev, DIR)
		return current

	# FIXME: remove in waf 1.6
	def exclusive_build_node(self, path):
		"""
		create a hierarchy in the build dir (no source folders) for ill-behaving compilers
		the node is not hashed, so you must do it manually

		after declaring such a node, find_dir and find_resource should work as expected
		"""
		lst = Utils.split_path(path)
		name = lst[-1]
		if len(lst) > 1:
			parent = None
			try:
				parent = self.find_dir(lst[:-1])
			except OSError:
				pass
			if not parent:
				# exclusive build directory -> mark the parent as rescanned
				# for find_dir and find_resource to work
				parent = self.ensure_dir_node_from_path(lst[:-1])
				self.__class__.bld.cache_scanned_folders[parent.id] = 1
			else:
				try:
					self.__class__.bld.rescan(parent)
				except OSError:
					pass
		else:
			parent = self

		node = parent.childs.get(name, None)
		if not node:
			node = self.__class__(name, parent, BUILD)

		return node

	def path_to_parent(self, parent):
		"path relative to a direct ancestor, as string"
		lst = []
		p = self
		h1 = parent.height()
		h2 = p.height()
		while h2 > h1:
			h2 -= 1
			lst.append(p.name)
			p = p.parent
		if lst:
			lst.reverse()
			ret = os.path.join(*lst)
		else:
			ret = ''
		return ret

	def find_ancestor(self, node):
		"find a common ancestor for two nodes - for the shortest path in hierarchy"
		dist = self.height() - node.height()
		if dist < 0: return node.find_ancestor(self)
		# now the real code
		cand = self
		while dist > 0:
			cand = cand.parent
			dist -= 1
		if cand == node: return cand
		cursor = node
		while cand.parent:
			cand = cand.parent
			cursor = cursor.parent
			if cand == cursor: return cand

	def relpath_gen(self, going_to):
		"string representing a relative path between self to another node"

		if self == going_to: return '.'
		if going_to.parent == self: return '..'

		# up_path is '../../../' and down_path is 'dir/subdir/subdir/file'
		ancestor = self.find_ancestor(going_to)
		lst = []
		cand = self
		while not cand.id == ancestor.id:
			lst.append(cand.name)
			cand = cand.parent
		cand = going_to
		while not cand.id == ancestor.id:
			lst.append('..')
			cand = cand.parent
		lst.reverse()
		return os.sep.join(lst)

	def nice_path(self, env=None):
		"printed in the console, open files easily from the launch directory"
		tree = self.__class__.bld
		ln = tree.launch_node()

		if self.id & 3 == FILE: return self.relpath_gen(ln)
		else: return os.path.join(tree.bldnode.relpath_gen(ln), env.variant(), self.relpath_gen(tree.srcnode))

	def is_child_of(self, node):
		"does this node belong to the subtree node"
		p = self
		diff = self.height() - node.height()
		while diff > 0:
			diff -= 1
			p = p.parent
		return p.id == node.id

	def variant(self, env):
		"variant, or output directory for this node, a source has for variant 0"
		if not env: return 0
		elif self.id & 3 == FILE: return 0
		else: return env.variant()

	def height(self):
		"amount of parents"
		# README a cache can be added here if necessary
		d = self
		val = -1
		while d:
			d = d.parent
			val += 1
		return val

	# helpers for building things

	def abspath(self, env=None):
		"""
		absolute path
		@param env: optional only if the node is a source node
		"""
		## absolute path - hot zone, so do not touch

		# less expensive
		variant = (env and (self.id & 3 != FILE) and env.variant()) or 0
		#variant = self.variant(env)
		ret = self.__class__.bld.cache_node_abspath[variant].get(self.id, None)
		if ret: return ret

		if not variant:
			if not self.parent:
				val = os.sep
			elif not self.parent.name:
				val = os.sep + self.name
			else:
				val = self.parent.abspath() + os.sep + self.name
		else:
			val = os.sep.join((self.__class__.bld.bldnode.abspath(), env.variant(), self.path_to_parent(self.__class__.bld.srcnode)))
		self.__class__.bld.cache_node_abspath[variant][self.id] = val
		return val

	def change_ext(self, ext):
		"node of the same path, but with a different extension - hot zone so do not touch"
		name = self.name
		k = name.rfind('.')
		if k >= 0:
			name = name[:k] + ext
		else:
			name = name + ext

		return self.parent.find_or_declare([name])

	def src_dir(self, env):
		"src path without the file name"
		return self.parent.srcpath(env)

	def bld_dir(self, env):
		"build path without the file name"
		return self.parent.bldpath(env)

	def bld_base(self, env):
		"build path without the extension: src/dir/foo(.cpp)"
		s = os.path.splitext(self.name)[0]
		return os.path.join(self.bld_dir(env), s)

	def bldpath(self, env=None):
		"path seen from the build dir default/src/foo.cpp"
		if self.id & 3 == FILE:
			return self.relpath_gen(self.__class__.bld.bldnode)
		if self.path_to_parent(self.__class__.bld.srcnode) is not '':
			return os.path.join(env.variant(), self.path_to_parent(self.__class__.bld.srcnode))
		return env.variant()

	def srcpath(self, env=None):
		"path in the srcdir from the build dir ../src/foo.cpp"
		if self.id & 3 == BUILD:
			return self.bldpath(env)
		return self.relpath_gen(self.__class__.bld.bldnode)

	def read(self, env):
		"get the contents of a file, it is not used anywhere for the moment"
		return Utils.readf(self.abspath(env))

	def dir(self, env):
		"scons-like"
		return self.parent.abspath(env)

	def file(self):
		"scons-like"
		return self.name

	def file_base(self):
		"scons-like"
		return os.path.splitext(self.name)[0]

	def suffix(self):
		"scons-like - hot zone so do not touch"
		k = max(0, self.name.rfind('.'))
		return self.name[k:]

	def find_iter_impl(self, src=True, bld=True, dir=True, accept_name=None, is_prune=None, maxdepth=25):
		"find nodes in the filesystem hierarchy, try to instanciate the nodes passively"
		self.__class__.bld.rescan(self)
		for name in self.__class__.bld.cache_dir_contents[self.id]:
			if accept_name(self, name):
				node = self.find_resource(name)
				if node:
					if src and node.id & 3 == FILE:
						yield node
				else:
					node = self.find_dir(name)
					if node and node.id != self.__class__.bld.bldnode.id:
						if dir:
							yield node
						if not is_prune(self, name):
							if maxdepth:
								for k in node.find_iter_impl(src, bld, dir, accept_name, is_prune, maxdepth=maxdepth - 1):
									yield k
			else:
				if not is_prune(self, name):
					node = self.find_resource(name)
					if not node:
						# not a file, it is a dir
						node = self.find_dir(name)
						if node and node.id != self.__class__.bld.bldnode.id:
							if dir:
								yield node
							if maxdepth:
								for k in node.find_iter_impl(src, bld, dir, accept_name, is_prune, maxdepth=maxdepth - 1):
									yield k

		if bld:
			for node in self.childs.values():
				if node.id == self.__class__.bld.bldnode.id:
					continue
				if node.id & 3 == BUILD:
					if accept_name(self, node.name):
						yield node
		raise StopIteration

	def find_iter(self, in_pat=['*'], ex_pat=[], prune_pat=['.svn'], src=True, bld=True, dir=False, maxdepth=25, flat=False):
		"find nodes recursively, this returns everything but folders by default"

		if not (src or bld or dir):
			raise StopIteration

		if self.id & 3 != DIR:
			raise StopIteration

		in_pat = Utils.to_list(in_pat)
		ex_pat = Utils.to_list(ex_pat)
		prune_pat = Utils.to_list(prune_pat)

		def accept_name(node, name):
			for pat in ex_pat:
				if fnmatch.fnmatchcase(name, pat):
					return False
			for pat in in_pat:
				if fnmatch.fnmatchcase(name, pat):
					return True
			return False

		def is_prune(node, name):
			for pat in prune_pat:
				if fnmatch.fnmatchcase(name, pat):
					return True
			return False

		ret = self.find_iter_impl(src, bld, dir, accept_name, is_prune, maxdepth=maxdepth)
		if flat:
			return " ".join([x.relpath_gen(self) for x in ret])

		return ret

	def ant_glob(self, *k, **kw):
		regex = Utils.jar_regexp(k[0])
		def accept(node, name):
			ts = node.relpath_gen(self) + '/' + name
			return regex.match(ts)

		def reject(node, name):
			ts = node.relpath_gen(self) + '/' + name
			return default_excludes()(ts)

		ret = [x for x in self.find_iter_impl(
			accept_name=accept,
			is_prune=reject,
			src=kw.get('src', 1),
			bld=kw.get('bld', 1),
			dir=kw.get('dir', 0),
			maxdepth=kw.get('maxdepth', 25)
			)]

		if kw.get('flat', True):
			return " ".join([x.relpath_gen(self) for x in ret])

		return ret

# win32 fixes follow
if sys.platform == "win32":
	def find_dir_win32(self, lst):

		if isinstance(lst, str):
			lst = Utils.split_path(lst)

		current = self
		for name in lst:
			self.__class__.bld.rescan(current)
			prev = current

			if not current.parent and name == current.name:
				continue
			if not name:
				continue
			elif name == '.':
				continue
			elif name == '..':
				current = current.parent or current
			else:
				current = prev.childs.get(name, None)
				if current is None:
					if (name in self.__class__.bld.cache_dir_contents[prev.id]
						or (not prev.parent and name[1] == ":")):
						current = self.__class__(name, prev, DIR)
					else:
						return None
		return current
	Node.find_dir = find_dir_win32

	def abspath_win32(self, env=None):
		variant = self.variant(env)
		ret = self.__class__.bld.cache_node_abspath[variant].get(self.id, None)
		if ret: return ret

		if not variant:
			cur = self
			lst = []
			while cur:
				lst.append(cur.name)
				cur = cur.parent
			lst.reverse()
			val = os.sep.join(lst)
		else:
			val = os.sep.join((self.__class__.bld.bldnode.abspath(), env.variant(), self.path_to_parent(self.__class__.bld.srcnode)))
		if val.startswith("\\"): val = val[1:]
		if val.startswith("\\"): val = val[1:]
		self.__class__.bld.cache_node_abspath[variant][self.id] = val
		return val
	Node.abspath = abspath_win32


class Nodu(Node):
	pass

