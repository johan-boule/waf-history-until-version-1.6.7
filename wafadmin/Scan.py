#! /usr/bin/env python
# encoding: utf-8
# Thomas Nagy, 2005 (ita)

"Scan for dependencies, compute task signatures"

import md5
import Params
from Params import debug, error
from Params import hash_sig_weak

g_all_scanners={}
"all instances of scanners"

# TODO double check for threading issues
class scanner:
	"TODO: call this a dependency manager (not a scanner), as it does scan and compute the signatures"

	def __init__(self):
		global g_all_scanners
		g_all_scanners[self.__class__.__name__] = self

	# ======================================= #
	# interface definition

	"TODO: add the manually added dependencies"
	"TODO: add the environment variables dependencies"

	# computes the signature for a task
	# returns a string
	def get_signature(self, task):
		ret = self.get_signature_impl(task)
		debug("scanner:get_signature(self, task) %s" % str(Params.vsig(ret)), 'scan')
		return ret

	# scans a node
	# this method takes as input a node and a list of paths
	# it searches dependencies in the paths, and returns a list
	# of nodes that should trigger a rebuild.

	# it returns a tuple containing:
	# * a list of nodes corresponding to real files
	# * a list of names for files not found in path_lst
	# the input parameters may have more parameters that the ones used below
	def scan(self, node, env, path_lst):
		return ([], [])

	# last minute check: may this task run?
	def may_start(self, task):
		return 1

	# re-scan a node, update the tree
	def do_scan(self, node, env, hashparams):
		debug("scanner:do_scan(self, node, env, hashparams)", 'scan')

		variant = node.variant(env)
		if not node:
			error("BUG rescanning a null node")
			return
		(nodes, names) = self.scan(node, env, **hashparams)
		if Params.g_zones: debug('scanner for %s returned %s %s' % (node.m_name, str(nodes), str(names)), 'scan')
		tree = Params.g_build

		tree.m_depends_on[variant][node] = nodes
		tree.m_raw_deps[variant][node] = names

		tree.m_deps_tstamp[variant][node] = tree.m_tstamp_variants[variant][node]

	# ======================================= #
	# private method

	def get_signature_impl(self, task):
		"TODO: the weak scheme is hardly ever used, provide a function for replacing the methods"
		m = md5.new()
		tree = Params.g_build
		seen = []
		env  = task.m_env
		variant = task.m_inputs[0].variant(env)
		def add_node_sig(node):
			if not node: print "warning: null node in get_node_sig"
			seen.append(node.m_name)

			# rescan if necessary, and add the signatures of the nodes it depends on
			if tree.needs_rescan(node, env): self.do_scan(node, env, task.m_scanner_params)
			try:
				lst = tree.m_depends_on[variant][node]
			except KeyError:
				lst = []
			for dep in lst:
				if not dep.m_name in seen:
					add_node_sig(dep)
			try:
				tstamp = tree.m_tstamp_variants[variant][node]
			except KeyError:
				## fallback to the timestamp in the source tree
				tstamp = tree.m_tstamp_variants[0][node]
			m.update(tstamp)

		# add the signatures of the input nodes
		for node in task.m_inputs: add_node_sig(node)

		# add the signatures of the task it depends on
		for task in task.m_run_after: m.update(task.signature())
		return m.digest()

	def get_signature_default_weak(self, task):
		msum = 0
		tree = Params.g_build
		seen = []
		env  = task.m_env
		variant = task.m_inputs[0].variant(env)
		def add_node_sig(node):
			if not node: print "warning: null node in get_node_sig"

			sum = 0
			seen.append(node.m_name)

			sum += tree.m_tstamp_variants[variant][node]
			# rescan if necessary, and add the signatures of the nodes it depends on
			if tree.needs_rescan(node, task.m_env): self.do_scan(node, task.m_env, task.m_scanner_params)
			try: lst = tree.m_depends_on[variant][node]
			except KeyError: lst = []
			for dep in lst:
				if not dep.m_name in seen:
					sum += add_node_sig(dep)
			return sum
		# add the signatures of the input nodes
		for node in task.m_inputs: msum = hash_sig_weak(msum, add_node_sig(node))
		# add the signatures of the task it depends on
		for task in task.m_run_after: msum = hash_sig_weak(msum, task.signature())
		return int(msum)

g_default_scanner = scanner()
"default scanner: unique instance"

