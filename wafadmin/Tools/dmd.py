#! /usr/bin/env python
# encoding: utf-8
# Carlos Rafael Giani, 2007 (dv)

import sys

def detect(conf):
	d_compiler = None
	if conf.env['D_COMPILER']:
		d_compiler = conf.env['D_COMPILER']
	if not d_compiler: d_compiler = conf.find_program('dmd', var='D_COMPILER')
	if not d_compiler:
		return 0

	conf.check_tool('d')

	conf.check_tool('ar')
	if not conf.env['AR']:
		conf.fatal('ar is needed for static libraries - not found')

	v = conf.env

	#compiler
	v['D_COMPILER']           = d_compiler

	# Compiler is dmd so 'gdc' part will be ignored, just
	# ensure key is there, so wscript can append flags to it
	v['DFLAGS']               = {'gdc': [], 'dmd': ['-version=Posix']}
	# Compiler-specific flags, are set to either v['DFLAGS']['gdc'] or ..['dmd']
	# during dobj.apply()
	v['_DFLAGS']              = []
	v['_DIMPORTFLAGS']        = []

	v['D_SRC_F']              = ''
	v['D_TGT_F']              = '-c -of'
	v['DPATH_ST']             = '-I%s' # template for adding import paths

	# linker
	v['D_LINKER']             = v['D_COMPILER']
	v['DLNK_SRC_F']           = ''
	v['DLNK_TGT_F']           = '-of'

	v['DLIB_ST']              = '-L-l%s' # template for adding libs
	v['DLIBPATH_ST']          = '-L-L%s' # template for adding libpaths
	v['_DLIBDIRFLAGS']        = ''
	v['_DLIBFLAGS']           = ''

	# linker debug levels
	v['DFLAGS_OPTIMIZED']      = ['-O']
	v['DFLAGS_DEBUG']          = ['-g', '-debug']
	v['DFLAGS_ULTRADEBUG']     = ['-g', '-debug']
	v['DLINKFLAGS']            = ['-quiet']
	v['DLINKFLAGS_OPTIMIZED']  = ['-O']
	v['DLINKFLAGS_RELEASE']    = ['-O']
	v['DLINKFLAGS_DEBUG']      = ['-g']
	v['DLINKFLAGS_ULTRADEBUG'] = ['-g', '-debug']


	if sys.platform == "win32":
		# shared library
		v['D_shlib_DFLAGS']        = []
		v['D_shlib_LINKFLAGS']     = []
		v['D_shlib_obj_ext']       = ['.os']
		v['D_shlib_PREFIX']        = 'lib'
		v['D_shlib_SUFFIX']        = '.dll'

		# static library
		v['D_staticlib_obj_ext']   = ['.o']
		v['D_staticlib_PREFIX']    = 'lib'
		v['D_staticlib_SUFFIX']    = '.a'

		# program
		v['D_program_obj_ext']     = ['.o']
		v['D_program_PREFIX']      = ''
		v['D_program_SUFFIX']      = '.exe'

	else:
		# shared library
		v['D_shlib_DFLAGS']        = []
		v['D_shlib_LINKFLAGS']     = []
		v['D_shlib_obj_ext']       = ['.os']
		v['D_shlib_PREFIX']        = 'lib'
		v['D_shlib_SUFFIX']        = '.so'

		# static lib
		v['D_staticlib_obj_ext']   = ['.o']
		v['D_staticlib_PREFIX']    = 'lib'
		v['D_staticlib_SUFFIX']    = '.a'

		# program
		v['D_program_obj_ext']     = ['.o']
		v['D_program_PREFIX']      = ''
		v['D_program_SUFFIX']      = ''

	v['program_INST_VAR'] = 'PREFIX'
	v['program_INST_DIR'] = 'bin'
	v['shlib_INST_VAR'] = 'PREFIX'
	v['shlib_INST_DIR'] = 'lib'
	v['staticlib_INST_VAR'] = 'PREFIX'
	v['staticlib_INST_DIR'] = 'lib'

	return 1

def set_options(opt):
	pass
