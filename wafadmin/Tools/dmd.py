#!/usr/bin/env python
# encoding: utf-8
# Carlos Rafael Giani, 2007 (dv)
# Thomas Nagy, 2008 (ita)

import sys
import Utils, ar
from Configure import conftest

@conftest
def find_dmd(conf):
	conf.find_program(['dmd', 'ldc'], var='D_COMPILER', mandatory=True)

@conftest
def common_flags_ldc(conf):
	v = conf.env
	v['DFLAGS']         = ['-d-version=Posix']
	v['DLINKFLAGS']     = []
	v['D_shlib_DFLAGS'] = ['-relocation-model=pic']

@conftest
def common_flags_dmd(conf):
	v = conf.env

	# _DFLAGS _DIMPORTFLAGS

	# Compiler is dmd so 'gdc' part will be ignored, just
	# ensure key is there, so wscript can append flags to it
	v['DFLAGS']            = ['-version=Posix']

	v['D_SRC_F']           = ''
	v['D_TGT_F']           = ['-c', '-of']
	v['DPATH_ST']          = '-I%s' # template for adding import paths

	# linker
	v['D_LINKER']          = v['D_COMPILER']
	v['DLNK_SRC_F']        = ''
	v['DLNK_TGT_F']        = '-of'

	v['DLIB_ST']           = '-L-l%s' # template for adding libs
	v['DLIBPATH_ST']       = '-L-L%s' # template for adding libpaths

	# linker debug levels
	v['DFLAGS_OPTIMIZED']  = ['-O']
	v['DFLAGS_DEBUG']      = ['-g', '-debug']
	v['DFLAGS_ULTRADEBUG'] = ['-g', '-debug']
	v['DLINKFLAGS']        = ['-quiet']

	v['D_shlib_DFLAGS']    = ['-fPIC']
	v['D_shlib_LINKFLAGS'] = ['-L-shared']

	v['DHEADER_ext']       = '.di'
	v['D_HDR_F']           = ['-H', '-Hf']

	binfmt = conf.env.DEST_BINFMT or Utils.unversioned_sys_platform_to_binary_format(
		conf.env.DEST_OS or Utils.unversioned_sys_platform())
	if binfmt == 'pe':
		v['D_program_PATTERN']   = '%s.exe'
		v['D_shlib_PATTERN']     = 'lib%s.dll'
		v['D_staticlib_PATTERN'] = 'lib%s.a'
	else:
		v['D_program_PATTERN']   = '%s'
		v['D_shlib_PATTERN']     = 'lib%s.so'
		v['D_staticlib_PATTERN'] = 'lib%s.a'

def detect(conf):
	conf.find_dmd()
	conf.check_tool('ar')
	conf.check_tool('d')
	conf.common_flags_dmd()

	if conf.env.D_LINKER == 'ldc':
		conf.common_flags_ldc()

