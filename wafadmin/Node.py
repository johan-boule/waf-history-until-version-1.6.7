#!/usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

"""
Node: filesystem structure, contains lists of nodes

IMPORTANT:
1. Each file/folder is represented by exactly one node.

2. Most would-be class properties are stored in Build: nodes to depend on, signature, flags, ..
unused class members increase the .wafpickle file size sensibly with lots of objects.

3. The build is launched from the top of the build dir (for example, in _build_/).

4. Node should not be instantiated directly.
Each instance of Build.BuildContext has a Node subclass.
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

		if parent and name in parent.childs:
			raise WafError('node %s exists in the parent files %r already' % (name, parent))

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
		raise WafError('nodes, you are doing it wrong')

	def __copy__(self):
		"nodes are not supposed to be copied"
		raise WafError('nodes are not supposed to be copied')

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
		parent.rescan()

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
		tree.node_sigs[child.id] = st
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
		parent.rescan()

		name = lst[-1]
		node = parent.childs.get(name, None)
		if node:
			tp = node.id & 3
			if tp != BUILD:
				raise WafError("find_or_declare returns a build node, not a source nor a directory %r" % lst)
			return node
		node = self.__class__(name, parent, BUILD)
		return node

	def find_dir(self, lst):
		"search a folder in the filesystem"

		if isinstance(lst, str):
			lst = Utils.split_path(lst)

		current = self
		for name in lst:
			current.rescan()
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
					if prev.id in dir_cont and name in dir_cont[prev.id]:
						if not prev.name:
							if os.sep == '/':
								# cygwin //machine/share
								dirname = os.sep + name
							else:
								# windows c:
								dirname = name
						else:
							# regular path
							dirname = prev.abspath() + os.sep + name
						if not os.path.isdir(dirname):
							return None
						current = self.__class__(name, prev, DIR)
					elif (not prev.name and len(name) == 2 and name[1] == ':') or name.startswith('\\\\'):
						# drive letter or \\ path for windows
						current = self.__class__(name, prev, DIR)
					else:
						return None
				else:
					if current.id & 3 != DIR:
						return None
		return current

	# FIXME: remove in waf 1.6 ?
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
				parent = self.ensure_dir_node_from_path(lst[:-1])
				parent.rescan()
			else:
				try:
					parent.rescan()
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

	def relpath_gen(self, from_node):
		"string representing a relative path between self to another node"

		if self == from_node: return '.'
		if from_node.parent == self: return '..'

		# up_path is '../../../' and down_path is 'dir/subdir/subdir/file'
		ancestor = self.find_ancestor(from_node)
		lst = []
		cand = self
		while not cand.id == ancestor.id:
			lst.append(cand.name)
			cand = cand.parent
		cand = from_node
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
		else: return os.path.join(tree.bldnode.relpath_gen(ln), self.relpath_gen(tree.srcnode))

	def is_child_of(self, node):
		"does this node belong to the subtree node"
		p = self
		diff = self.height() - node.height()
		while diff > 0:
			diff -= 1
			p = p.parent
		return p.id == node.id

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

	def abspath(self):
		"""
		absolute path
		cache into the build context, cache_node_abspath
		"""
		## absolute path - hot zone, so do not touch

		ret = self.__class__.bld.cache_node_abspath.get(self.id, None)
		if ret: return ret

		id = self.id
		if id & 3 == BUILD:
			val = os.sep.join((self.__class__.bld.bldpath, self.path_to_parent(self.__class__.bld.srcnode)))
		else:
			if not self.parent:
				val = os.sep == '/' and os.sep or ''
			elif not self.parent.name: # root
				val = (os.sep == '/' and os.sep or '') + self.name
			else:
				val = self.parent.abspath() + os.sep + self.name

		self.__class__.bld.cache_node_abspath[id] = val
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

	def src_dir(self):
		"src path without the file name"
		return self.parent.srcpath()

	def bld_dir(self):
		"build path without the file name"
		return self.parent.bldpath()

	def bld_base(self):
		"build path without the extension: src/dir/foo(.cpp)"
		s = os.path.splitext(self.name)[0]
		return self.bld_dir() + os.sep + s

	def bldpath(self):
		"path seen from the build dir default/src/foo.cpp"
		if self.id & 3 == FILE:
			return self.relpath_gen(self.__class__.bld.bldnode)
		if self.path_to_parent(self.__class__.bld.srcnode) is not '':
			return self.path_to_parent(self.__class__.bld.srcnode)
		return '.'

	def srcpath(self):
		"path in the srcdir from the build dir ../src/foo.cpp"
		if self.id & 3 == BUILD:
			return self.bldpath()
		return self.relpath_gen(self.__class__.bld.bldnode)

	def read(self):
		"get the contents of a file, it is not used anywhere for the moment"
		return Utils.readf(self.abspath())

	def dir(self):
		"scons-like"
		return self.parent.abspath()

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
		bld_ctx = self.__class__.bld
		self.rescan()
		for name in bld_ctx.cache_dir_contents[self.id]:
			if accept_name(self, name):
				node = self.find_resource(name)
				if node:
					if src and node.id & 3 == FILE:
						yield node
				else:
					node = self.find_dir(name)
					if node and node.id != bld_ctx.bldnode.id:
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
						if node and node.id != bld_ctx.bldnode.id:
							if maxdepth:
								for k in node.find_iter_impl(src, bld, dir, accept_name, is_prune, maxdepth=maxdepth - 1):
									yield k

		if bld:
			for node in self.childs.values():
				if node.id == bld_ctx.bldnode.id:
					continue
				if node.id & 3 == BUILD:
					if accept_name(self, node.name):
						yield node
		raise StopIteration

	def find_iter(self, in_pat=['*'], ex_pat=exclude_pats, prune_pat=prune_pats, src=True, bld=True, dir=False, maxdepth=25, flat=False):
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
			nodi.rescan()
			for name in nodi.__class__.bld.cache_dir_contents[nodi.id]:
				npats = accept(name, pats)
				if npats and npats[0]:
					accepted = [] in npats[0]
					#print accepted, nodi, name

					node = nodi.find_resource(name)
					if node and accepted:
						if src and node.id & 3 == FILE:
							yield node
					else:
						node = nodi.find_dir(name)
						if node and node.id != nodi.__class__.bld.bldnode.id:
							if accepted and dir:
								yield node
							if maxdepth:
								for k in ant_iter(node, maxdepth=maxdepth - 1, pats=npats):
									yield k
			if bld:
				for node in nodi.childs.values():
					if node.id == nodi.__class__.bld.bldnode.id:
						continue
					if node.id & 3 == BUILD:
						npats = accept(node.name, pats)
						if npats and npats[0] and [] in npats[0]:
							yield node
			raise StopIteration

		ret = [x for x in ant_iter(self, pats=[to_pat(incl), to_pat(excl)])]

		if kw.get('flat', True):
			return " ".join([x.relpath_gen(self) for x in ret])

		return ret


	def rescan(self):
		"""
		look the contents of a (folder)node and update its list of childs

		The intent is to perform the following steps
		* remove the nodes for the files that have disappeared
		* remove the signatures for the build files that have disappeared
		* cache the results of os.listdir
		* create the build folder equivalent (mkdir)
		src/bar -> build/default/src/bar, build/release/src/bar

		when a folder in the source directory is removed, we do not check recursively
		to remove the unused nodes. To do that, call 'waf clean' and build again.
		"""

		bld = self.__class__.bld

		# do not rescan over and over again
		if bld.cache_scanned_folders.get(self.id, None):
			return

		# first, take the case of the source directory
		try:
			lst = set(Utils.listdir(self.abspath()))
		except OSError:
			lst = set([])

		bld.cache_dir_contents[self.id] = lst

		# hash the existing source files, remove the others
		cache = bld.node_sigs
		for x in self.childs.values():
			if x.id & 3 != Node.FILE: continue
			if x.name in lst:
				try:
					cache[x.id] = Utils.h_file(x.abspath())
				except IOError:
					raise WafError('The file %s is not readable or has become a dir' % x.abspath())
			else:
				try: del cache[x.id]
				except KeyError: pass

				del self.childs[x.name]

		if not bld.srcnode:
			# do not look at the build directory yet
			return
		bld.cache_scanned_folders[self.id] = True

		# first obtain the differences between srcnode and self
		h1 = bld.srcnode.height()
		h2 = self.height()

		lst = []
		child = self
		while h2 > h1:
			lst.append(child.name)
			child = child.parent
			h2 -= 1
		lst.reverse()

		# list the files in the build directory
		try:
			sub_path = os.path.join(bld.out_dir, *lst)
			bld.listdir_bld(self, sub_path)
			i_existing_nodes = [x for x in parent_node.childs.values() if x.id & 3 == Node.BUILD]

			lst = set(Utils.listdir(path))
			node_names = set([x.name for x in i_existing_nodes])
			remove_names = node_names - lst

			# remove the stamps of the build nodes that no longer exist on the filesystem
			ids_to_remove = [x.id for x in i_existing_nodes if x.name in remove_names]
			cache = bld.node_sigs
			for nid in ids_to_remove:
				try:
					cache.__delitem__(nid)
				except KeyError:
					pass

		except OSError:

			for node in self.childs.values():
				if node.id & 3 != Node.BUILD:
					continue
				bld.node_sigs.__delitem__(node.id)

				# the policy is to avoid removing nodes representing directories
				self.childs.__delitem__(node.name)

			sub_path = os.path.join(bld.outdir , *lst)
			try:
				os.makedirs(sub_path)
			except OSError:
				pass


class Nodu(Node):
	pass

