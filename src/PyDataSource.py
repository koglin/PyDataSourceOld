
# File and Version Information:
#  $HeaderURL$
#  $Id$
#  $LastChangedDate$
#
# Description:
#  module PyDataSource
#--------------------------------------------------------------------------
"""
Python implementation of psana DataSource object.

Example:

    # Import the PyDataSource module
    In [1]: import PyDataSource

    # Load example run
    In [2]: ds = PyDataSource.DataSource('exp=xpptut15:run=54')

    # Access the first event
    In [3]: evt = ds.events.next()

    # Tab to see Data objects in current event
    In [4]: evt.
    evt.EBeam            evt.FEEGasDetEnergy  evt.XppEnds_Ipm0     evt.cspad            evt.next
    evt.EventId          evt.L3T              evt.XppSb2_Ipm       evt.get              evt.yag2
    evt.Evr              evt.PhaseCavity      evt.XppSb3_Ipm       evt.keys             evt.yag_lom

    # Tab to see EBeam attributes
    In [4]: evt.EBeam.
    evt.EBeam.EventId            evt.EBeam.ebeamEnergyBC1     evt.EBeam.ebeamPhotonEnergy  evt.EBeam.epicsData
    ...
    evt.EBeam.ebeamDumpCharge    evt.EBeam.ebeamLTUPosY       evt.EBeam.ebeamXTCAVPhase    

    # Print a table of the EBeam data for the current event
    In [4]: evt.EBeam.show_info()
    --------------------------------------------------------------------------------
    EBeam xpptut15, Run 54, Step -1, Event 0, 11:37:12.4517, [140, 141, 41, 40]
    --------------------------------------------------------------------------------
    damageMask                 1.0486e+06         Damage mask.
    ebeamCharge                0.00080421 nC      Beam charge in nC.
    ...
    ebeamPhotonEnergy                   0 eV      computed photon energy, in eV
    ...

    # Print summary of the cspad detector (uses PyDetector methods for creatining calib and image data)
    In [5]: evt.cspad.show_info()
    --------------------------------------------------------------------------------
    cspad xpptut15, Run 54, Step -1, Event 0, 11:37:12.4517, [140, 141, 41, 40]
    --------------------------------------------------------------------------------
    calib                <0.010653> ADU     Calibrated data
    image               <0.0081394> ADU     Reconstruced 2D image from calibStore geometry
    raw                    <1570.2> ADU     Raw data
    shape              (32, 185, 388)         Shape of raw data array
    size                  2.297e+06         Total size of raw data

    # Print summary of cspad detector calibration data (using PyDetector access methods) 
    In [6]: evt.cspad.calibData.show_info()
    areas                  <1.0077>         Pixel area correction factor
    bkgd                      <0.0>         
    ...
    shape              (32, 185, 388)         Shape of raw data array
    size                  2.297e+06         Total size of raw data
    status             <0.00069396>         

    # Print summary of cspad detector calibration data (using PyDetector access methods) 
    In [7]: evt.cspad.configData.show_info()
    activeRunMode                       3         
    asicMask                           15         
    ...
    roiMasks                   0xffffffff         
    runDelay                        58100         
    tdi                                 4         

This software was developed for the LCLS project.
If you use all or part of it, please give an appropriate acknowledgment.

@version $Id$

@author Koglin, Jason
"""
#------------------------------
__version__ = "$Revision$"
##-----------------------------

import os
import sys
import operator
import imp
import re
import time
import traceback
import inspect

from pylab import *
import pandas as pd

# psana modules
import psana

from psmon import publish
publish.client_opts.daemon = True
from psmon.plots import Image, XYPlot, MultiPlot

# PyDataSource modules
from DataSourceInfo import *
from psana_doc_info import * 
from psmessage import Message

_eventCodes_rate = {
        40: '120 Hz',
        41: '60 Hz',
        42: '30 Hz',
        43: '10 Hz',
        44: '5 Hz',
        45: '1 Hz',
        46: '0.5 Hz',
        140: 'Beam & 120 Hz',
        141: 'Beam & 60 Hz',
        142: 'Beam & 30 Hz',
        143: 'Beam & 10 Hz',
        144: 'Beam & 5 Hz',
        145: 'Beam & 1 Hz',
        146: 'Beam & 0.5 Hz',
        150: 'Burst',
        162: 'BYKIK',
        163: 'BAKIK',
        }

def getattr_complete(base, args):
    """
    Recursive getattr
    
    Parameters
    ----------
    base : object
        Object

    args : str
        Argument to get from object
    """
    attrs = args.split('.')
    while len(attrs) > 0:
        base = getattr(base, attrs.pop(0))

    return base

def import_module(module_name, module_path):
    """
    Import a module from a given path.

    Parameters
    ----------
    module_name : str
        Name of module
    module_path : str
        Path of module
    """
    try:
        if not isinstance(module_path,list):
            module_path = [module_path]
        file,filename,desc = imp.find_module(module_name, module_path)
        globals()[module_name] = imp.load_module(module_name, file, filename, desc)
        return
    except Exception as err:
        print 'import_module error', err
        print 'ERROR loading {:} from {:}'.format(module_name, module_path)
        traceback.print_exc()

    sys.exit()

def get_module(module_name, module_path, reload=False):
    """
    Get module from path

    Parameters
    ----------
    module_name : str
        Name of module
    module_path : str
        Path of module
    reload : bool
        Reload module
    """
    if reload or module_name not in globals():
        import_module(module_name, module_path)
    
    try:
        new_class =  getattr(globals()[module_name],module_name)
    except:
        new_class =  getattr(globals()[module_name],module_name.capitalize())

    return new_class

def get_key_info(psana_obj):
    """Get a dictionary of the (type, src, key) for the data types of each src.
    """
    key_info = {}
    for key in psana_obj.keys():
        typ = key.type()
        src = key.src()
        if typ:
            srcstr = str(src)
            if srcstr not in key_info:
                key_info[srcstr] = [] 
            key_info[srcstr].append((typ, src, key.key()))

    return key_info

def get_keys(psana_obj):
    """Get a dictionary of the (type, src, key) for the data types of each src.
    """
    key_info = {}
    _modules = {}
    for key in psana_obj.keys():
        typ = key.type()
        src = key.src()
        if typ:
            srcstr = str(src)
            if srcstr not in key_info:
                key_info[srcstr] = [] 
            
            key_info[srcstr].append((typ, src, key.key()))
            
            type_name = typ.__name__
            module = typ.__module__.lstrip('psana.')
            if module:
                if module not in _modules:
                    _modules[module] = {}
                
                if type_name not in _modules[module]:
                    _modules[module][type_name] = []

                _modules[module][type_name].append((typ, src, key.key()))

    return key_info, _modules


def _repr_value(value):
    """Represent a value for use in show_info method.
    """
    if isinstance(value,str):
        return value
    else:
        if isinstance(value, list):
            if len(value) > 4:
                return 'list'
            else:
                return str(value)
        
        elif isinstance(value, int):
            return str(value)
        
        elif hasattr(value, 'mean') and value.size > 4:
            try:
                return '<{:.4}>'.format(value.mean())
            except:
                return str(value)
        
        else:
            try:
                return '{:10.5g}'.format(value)
            except:
                try:
                    return str(value)
                except:
                    return value

def _is_psana_type(value):
    """True if the input is a psana data type
    """
    return hasattr(value, '__module__') and value.__module__.startswith('psana')

def _get_typ_func_attr(typ_func, attr, nolist=False):
    """Return psana functions as properties.
    """
    value = getattr(typ_func, attr)
    module = typ_func.__module__.lstrip('psana.')
    type_name = typ_func.__class__.__name__
    try: 
        info = psana_doc_info[module][type_name].get(attr, {'unit': '', 'doc': ''}).copy()
    except:
        info = {'unit': '', 'doc': ''}

    info['typ_func'] = typ_func
    info['attr'] = attr

    if info.get('func_shape'):
        nvals = info.get('func_shape')
        if isinstance(nvals, str):
            nvals = getattr(typ_func, nvals)()[0]
       
        i0 = info.get('func0',0)
        try:
            value = [value(i+i0) for i in range(nvals)]
        except:
            pass

    elif info.get('func_len_hex'):
        nvals = getattr(typ_func, info.get('func_len_hex'))()
        try:
            value = [hex(value(i)) for i in range(nvals)]
        except:
            pass

    elif info.get('func_len'):
        nvals = info.get('func_len')
        if isinstance(nvals, str):
            nvals = getattr(typ_func, nvals)()
        
        try:
            value = [value(i) for i in range(nvals)]
        except:
            pass

    elif info.get('func_index'):
        vals = getattr(typ_func, info.get('func_index'))()
        try:
            value = [value(int(i)).name for i in vals]
        except:
            pass

    elif 'func_method' in info:
        info['value'] = info.get('func_method')(value())
        return info


    if hasattr(value, '_typ_func') and str(value._typ_func)[0].islower():
        # evaluate as name to avoid recursive psana functions 
        if 'name' in value._attrs and 'conjugate' in value._attrs:   
            info['value'] = value.name
  
    try:
        value = value()
        if hasattr(value, 'name'):
            info['value'] = value.name
            return info
    except:
        pass

    if isinstance(value, list):
        values = []
        is_type_list = False
        nvals = info.get('list_len', len(value))
        if isinstance(nvals, str):
            nvals = getattr(typ_func, nvals)()
       
        for i in range(nvals):
            val = value[i]
            if _is_psana_type(val):
                values.append(PsanaTypeData(val))
                is_type_list = True
            else:
                values.append(val)

        if is_type_list: # and not nolist:
            values = PsanaTypeList(values)

        info['value'] = values
        return info

    if _is_psana_type(value):
        info['value'] = PsanaTypeData(value)
    else:
        info['value'] = value

    return info

def psmon_publish(evt, quiet=True):
    eventCodes = evt.Evr.eventCodes
    event_info = str(evt)
    for alias in evt._attrs:
        psplots = evt._ds._device_sets.get(alias, {}).get('psplot')
        if psplots:
            detector = evt._dets.get(alias)
            for name, psmon_args in psplots.items():
                eventCode = psmon_args['pubargs'].get('eventCode', None)
                if not quiet:
                    print eventCode, name, psmon_args
                
                if eventCode is None or eventCode in eventCodes:
                    psplot_func = psmon_args['plot_function']
                    psmon_fnc = None
                    if psplot_func is 'Image':
                        image = getattr_complete(detector, psmon_args['attr'][0])
                        if not quiet:
                            print name, image
                        if image is not None:
                            psmon_fnc = Image(
                                        event_info,
                                        psmon_args['title'],
                                        np.array(image, dtype='f'), 
                                        #np.array(image, dtype='f').transpose(), 
                                        **psmon_args['kwargs'])
                    
                    elif psplot_func is 'XYPlot':
                        ydata = np.array([getattr_complete(detector, attr) \
                                for attr in psmon_args['attr']], dtype='f').squeeze()
                        if ydata is not None:
                            if not quiet:
                                print event_info
                                print psmon_args['title']
                                print psmon_args['xdata'].shape
                                print np.array(ydata, dtype='f')
                            
                            psmon_fnc = XYPlot(
                                        event_info,
                                        psmon_args['title'],
                                        psmon_args['xdata'],
                                        ydata,
                                        **psmon_args['kwargs'])

                    if psmon_fnc:
                        #print 'publish', name, event_info, psmon_args
                        #print psmon_fnc
                        pub_info = publish.send(name,psmon_fnc)
                        psmon_args['psmon_fnc'] = psmon_fnc


class ScanData(object):
    """
    Scan configuration for Run
    
    Information from daq-scan, where things like motor positions are changed during a run 
    in "steps" or "calibcycles".

    Parameters
    ----------
    ds : object
        PyDataSource.DataSource object

    Attributes
    ----------
    nevents : list
        Number of events for each step

    """
    _array_attrs = ['pvControls_value', 'pvMonitors_loValue', 'pvMonitors_hiValue']
    _uses_attrs = ['uses_duration', 'uses_events', 'uses_l3t_events']
    _npv_attrs = ['npvControls', 'npvMonitors']

    def __init__(self, ds):
        self._ds = ds
        self._attrs = sorted(ds.configData.ControlData._all_values.keys())
        self._scanData = {attr: [] for attr in self._attrs}
        ds.reload()
        self.nsteps = ds._idx_nsteps
        start_times = []
        ievent_end = []
        ievent_start = []
        for istep, events in enumerate(ds.steps):
            okevt = False
            while not okevt:
                evt = events.next()
                ttup = (evt.EventId.sec, evt.EventId.nsec, evt.EventId.fiducials)
                okevt = ttup in ds._idx_times_tuple

            ievent = ds._idx_times_tuple.index(ttup)
            ievent_start.append(ievent)
            if istep > 0:
                ievent_end.append(ievent-1)
            start_times.append(evt.EventId.timef64) 
 
            for attr in self._attrs:
                self._scanData[attr].append(ds.configData.ControlData._all_values[attr])
        
        ievent_end.append(len(ds._idx_times_tuple)-1)       
        end_times = []
        for istep, ievent in enumerate(ievent_end):
            end_times.append(ds.events.next(ievent).EventId.timef64)
 
        self._scanData['ievent_start'] = np.array(ievent_start)
        self._scanData['ievent_end'] = np.array(ievent_end)
        self.nevents = np.array(ievent_end)-np.array(ievent_start)       
        self.start_times = np.array(start_times)
        self.end_times = np.array(end_times)
        self.step_times = np.array(end_times) - np.array(start_times)
 
        for attr in self._uses_attrs:
            setattr(self, attr, all(self._scanData.get(attr)))

        if (self.uses_duration or self.uses_events or self.uses_l3t_events) \
                and len(set(self._scanData['npvControls'])) == 1 \
                and len(set(self._scanData['npvMonitors'])) == 1 :
            self._is_simple = True
            for attr in self._npv_attrs:
                setattr(self, attr, self._scanData.get(attr)[0]) 

            if 'pvControls_name' in self._attrs:
                self.pvControls = self._scanData['pvControls_name'][0]
            else:
                self.pvControls = []
            
            if 'pvMonitors_name' in self._attrs:
                self.pvMonitors = self._scanData['pvMonitors_name'][0]
            else:
                self.pvMonitors = None

            self.pvLabels = self._scanData['pvLabels'][0]
            if not self.pvLabels:
                self.pvLabels = []
                for pv in self.pvControls:
                    alias = ds.epicsData.alias(pv)
                    if not alias:
                        alias = pv

                    self.pvLabels.append(alias) 
            
            self.control_values = {} 
            self.monitor_hivalues = {}
            self.monitor_lovalues = {}
            if self.pvControls is not None:
                for i, pv in enumerate(self.pvControls):
                    self.control_values[pv] = \
                            np.array([val[i] for val in self._scanData['pvControls_value']])
                
            if self.pvMonitors is not None:
                for i, pv in enumerate(self.pvMonitors):
                    self.monitor_hivalues[pv] = \
                            np.array([val[i] for val in self._scanData['pvMonitors_hiValue']])
                    self.monitor_lovalues[pv] = \
                            np.array([val[i] for val in self._scanData['pvMonitors_loValue']])

            self.pvAliases = {}
            for i, pv in enumerate(self.pvControls):
                alias = self.pvLabels[i]
                self.pvAliases[pv] = re.sub('-|:|\.| ','_', alias)
                setattr(self, alias, self.control_values[pv])

        ds.reload()

    def show_info(self, **kwargs):
        """Show scan information.
        """
        message = Message(quiet=True, **kwargs)
        
        attrs = { 
            'nsteps':      {'unit': '',     'desc': 'Number of steps'}, 
            'npvControls': {'unit': '',     'desc': 'Number of control PVs'},
            'npvMonitors': {'unit': '',     'desc': 'Number of monitor PVs'},
            }

        message('{:10}: Run {:}'.format(self._ds.data_source.exp, self._ds.data_source.run))
        message('-'*70)
        for attr, item in attrs.items():
            message('{:24} {:10} {:16}'.format(item.get('desc'), getattr(self, attr), attr))
       
        message('')
        message('{:24} {:40}'.format('Alias', 'PV'))
        message('-'*70)
        for name, alias in self.pvAliases.items():
            message('{:24} {:40}'.format(alias, name))
        message('')

        self._control_format = {}
        self._name_len = {}
        header1 = '{:4} {:6} {:>10}'.format('Step', 'Events', 'Time [s]')
        for i, name in enumerate(self.control_values):
            alias = self.pvAliases.get(name, name)
            name_len = len(alias)
            self._name_len[name] = name_len 
            name_format = ' {:>'+str(name_len)+'}'
            header1 += name_format.format(alias)
            vals = self.control_values[name]
            if self.nsteps > 1:
                meanvals = np.mean(abs(vals[1:]-vals[:-1]))
                if meanvals > 0:
                    sigdigit = int(np.floor(np.log10(meanvals)))
                else:
                    sigdigit = -2
            else:
                sigdigit = int(np.floor(np.log10(abs(vals))))
            
            if sigdigit < -5 or sigdigit > 5:
                self._control_format[name] = ' {:'+str(name_len)+'.3e}'
            elif sigdigit < 0:
                self._control_format[name] = ' {:'+str(name_len)+'.'+str(-sigdigit+1)+'f}'
            else:
                self._control_format[name] = ' {:'+str(name_len)+'}'

        message(header1)
        message('-'*(21+int(sum(self._name_len.values()))))
        for i, nevents in enumerate(self.nevents):
            a = '{:4} {:6} {:8.3f}'.format(i, nevents, self.step_times[i])
            for name, vals in self.control_values.items():
                a += self._control_format[name].format(vals[i])
            
            message(a)

        return message

    def __str__(self):
        return  'ScanData: '+str(self._ds.data_source)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        print '< '+repr_str+' >'
        self.show_info()
        return '< '+repr_str+' >'


class DataSource(object):
    """
    Python version of psana.DataSource with support for event and config
    data as well as PyDetector functions to access calibrated data.

    data_source string is build by DataSourceInfo object if not passed 
    directly as data_source string.
    
    Parameters 
    ----------
    data_source : str
        name of data source using psana convention (e.g., 'exp=xpptut15:run=54:smd')

    exp : str
        experiment name (e.g., exp='xpptut15')

    run : int
        run number (e.g., run=54)

    smd : bool , optional
        small data support -- default for experiments after Oct 2015 when this feature became standard 

    Attributes
    ----------
    data_source :  object
        DataSourceInfo object

    steps : object
        Steps object

    epicsData : object

    configData : object

    """

    _ds_funcs = ['end', 'env']
    _ds_attrs = ['empty']
    _env_attrs = ['calibDir', 'instrument', 'experiment','expNum']
#    _plugins = {}
#    _default_plugins = ['psplot.Psplot']
    _default_modules = {
            'path': '',
            'devName': {
##                'Evr': 'evr', 
##                'Imp': 'imp',
#                'Acqiris': 'acqiris',
##                'Epix': 'epix100',
##                'Cspad': 'cspad',
##                'Cspad2x2': 'cspad2x2',
##                'Tm6740': 'pim',
##                'Opal1000': 'camera',
##                'Opal2000': 'camera',
##                'Opal4000': 'camera',
##                'Opal8000': 'camera',
                },
             'srcname': {
#                'XrayTransportDiagnostic.0:Opal1000.0': 'xtcav_det',
#                'CxiDsu.0:Opal1000.0': 'timetool',     
                },
            }


    def __init__(self, data_source=None, **kwargs):
        self._device_sets = {}
        path = os.path.dirname(__file__)
        if not path:
            path = '.'

        self._default_modules.update({'path': path})
        #self._default_modules.update({'path': os.path.join(path,'detectors')})
        self.load_run(data_source=data_source, **kwargs)
        if self.data_source.smd:
            self._load_smd_config()

    def _load_smd_config(self):
        """Load configData of first calib cycle by going to first step.
           Reload so that steps can be used as an iterator.
        """
        if self.data_source.smd:
            step = self.steps.next()
            self.reload()
    
    def load_run(self, data_source=None, reload=False, **kwargs):
        """Load a run with psana.
        """
        self._evtData = None
        self._current_evt = None
        self._current_step = None
        self._current_run = None
        self._evt_keys = {}
        self._evt_modules = {}
        self._init_dets = []
        if not reload:
            self.data_source = DataSourceInfo(data_source=data_source, **kwargs)

        # do not reload shared memory
        if not (self.data_source.monshmserver and self._ds):
            if True:
                self._ds = psana.DataSource(str(self.data_source))
                _key_info, _modules = get_keys(self._ds.env().configStore())
                if 'Partition' in _modules:
                    try_idx = False

                else:
                    #if not self.data_source.smd:
                    if False:
                        print 'Exp {:}, run {:} is has no Partition data.'.format( \
                            self.data_source.exp, self.data_source.run)
                        print 'PyDataSource requires Partition data.'
                        print 'Returning psana.DataSource({:})'.format(str(self.data_source))
                        return self._ds
                    else:
                        try_idx = True
                        print 'Exp {:}, run {:} smd data has no Partition data -- loading idx data instead.'.format( \
                            self.data_source.exp, self.data_source.run)
            else:
                try_idx = True
                print 'Exp {:}, run {:} smd data file not available -- loading idx data instead.'.format( \
                            self.data_source.exp, self.data_source.run)

        if try_idx:
            if self.data_source.smd:
                try:
                    print 'Use smldata executable to convert idx data to smd data.'
                    data_source_smd = self.data_source
                    data_source_idx = str(data_source_smd).replace('smd','idx')
                    self.data_source = DataSourceInfo(data_source=data_source_idx)
                    self._ds = psana.DataSource(str(self.data_source))
                except:
                    print 'Failed to load either smd or idx data for exp {:}, run {:}'.format( \
                            self.data_source.exp, self.data_source.run)
                    print 'Data can be restored from experiment data portal:  https://pswww.slac.stanford.edu'
                    return False

        self.epicsData = EpicsData(self._ds) 

        self._evt_time_last = (0,0)
        self._ievent = -1
        self._istep = -1
        self._irun = -1
        if self.data_source.idx:
            self.runs = Runs(self, **kwargs)
            self.events = self.runs.next().events
        
        elif self.data_source.smd:
            self.steps = Steps(self, **kwargs)
            # SmdEvents automatically goes to next step if no events in current step.
            self.events = SmdEvents(self)
            if not reload:
                self._scanData = None
                data_source_idx = str(self.data_source).replace('smd','idx')
                self._idx_ds = psana.DataSource(data_source_idx)
                self._idx_run = self._idx_ds.runs().next()
                self._idx_nsteps = self._idx_run.nsteps()
                self._idx_times = self._idx_run.times()
                self.nevents = len(self._idx_times)
                self._idx_times_tuple = [(a.seconds(), a.nanoseconds(), a.fiducial()) \
                                        for a in self._idx_times]
        
        else:
            # For live data or data_source without idx or smd
            self.events = Events(self)
            self.nevents = None

        return str(self.data_source)

    def reload(self):
        """Reload the current run.
        """
        self.load_run(reload=True)

    def _load_ConfigData(self):
        self._ConfigData = ConfigData(self)

    def to_xarray(self, **kwargs):
        """
        Build xarray object from PyDataSource.DataSource object.
        
        See Also
        --------
        PyDataSource.psxarray.to_xarray

        Example
        -------
        import PyDataSource
        ds = PyDataSource.DataSource(exp='xpptut15',run=200)
        evt = ds.events.next()
        evt.opal_1.add.projection('raw', axis='x', roi=((0,300),(1024,400)))
        evt.cs140_rob.add.roi('calib',sensor=1,roi=((104,184),(255,335)))
        evt.cs140_rob.add.count('roi')
        x = ds.to_xarray()
        # Takes ~30 min to create in single core.
        # Saved file 2 GB
 
        """
        from psxarray import to_xarray
        return to_xarray(self, **kwargs)

    @property
    def configData(self):
        """
        Configuration Data from ds.env().configStore().
        For effieciency only loaded at beginning of run or step unless
        working with shared memory.
        
        See Also
        --------
        ConfigData : class
            Configuation Data Access  
        
          
        """
        if self.data_source.monshmserver:
            self._load_ConfigData()
        
        return self._ConfigData

    @property
    def scanData(self):
        """
        ScanData
        
        See Also
        --------
        ScanData : class
            Scan Data Access  
        """
        return self.configData.ScanData

    @property
    def sources(self):
        """
        Detector sources
        
        See Also
        --------
        Sources : class
            Event data sources

        """
        return self.configData.Sources

    def _init_detectors(self):
        """Initialize psana.Detector classes based on psana env information.
        """
        self._detectors = {}
        self._load_ConfigData()
        self._aliases = self.configData._aliases
        for srcstr, item in self.configData._sources.items():
            alias = item.get('alias')
            self._add_dets(**{alias: srcstr})

    def add_detector(self, srcstr=None, alias=None, module=None, path=None, 
                     #pvs=None, desc=None, parameters={}, 
                     desc=None,
                     quiet=False,
                     **kwargs):
        """
        Add a detector 
        
        Parameters
        ----------

        srcstr : str
            Source string name or alias of detector

        alias : str
            Detector alias -- default uses srcstr

        module : str
            Name of python module that contains a user defined PyDataSource.Detector class
            with the same name as the module.  e.g., 'acqiris' loads 'acqiris.py' file 
            which must have class Acqiris(PyDatasource.Detector)

        path : str
            Name of path for python module (default is the path of PyDataSource)

        desc : str
            Description 

        """
        initialized = False
        if not alias:
            if not srcstr:
                print 'Source string name or alias must be supplied'
            elif srcstr in self._aliases:
                alias = srcstr
                srcstr = self._aliases[alias]
            else:
                alias = re.sub('-|:|\.| ','_', srcstr)

        det = alias
        
        if alias not in self._device_sets:
            self._device_sets[alias] = {
                    'alias': alias, 
                    'module': {},
                    'opts': {}, 
                    'parameter': {}, 
                    'property': {},
                    'psplot': {},
                    'roi': {},
                    'count': {},
                    'peak': {},
                    'histogram': {},
                    'projection': {},
                    'xarray': {},
                    }

            if not desc:
                desc = alias
        
        if True:
            srcname = srcstr.split('(')[1].split(')')[0]
            try:
                devName = srcname.split(':')[1].split('.')[0]
            except:
                devName = None

            det_dict = self._device_sets[alias]
            det_dict.update({'desc': desc, 'srcname': srcname, 'srcstr': srcstr, 'devName': devName})
            
            if module:
                module = module.split('.')[0]

            # First check for device configuration
            
            if det_dict.get('module'):
                module_name = det_dict['module'].get('name',None)
                module_path = det_dict['module'].get('path','')
#                module_name = det_dict['module'].get('name',None)
#                if 'path' in det_dict['module']:
#                    module_path = det_dict['module'].get('path','')
#                else:
#                    module_path = ''
            else:
                module_name = None 
                module_path = ''

            # Then use module and path keywords if applicable
            if module:
                if module_name:
                    if not quiet:
                        print 'Changing {alias} detector module from \
                              {module_name} to {module}'.format(
                               alias=alias,module=module,module_name=module_name)
                else:
                    det_dict['module'] = {}
                
                module_name = module
                det_dict['module']['name'] = module

            # Use defaults if not set by keyword or in device config
            if not module_name: 
                if srcname in self._default_modules['srcname']:
                    module_name = self._default_modules['srcname'][srcname]
                    module_path = ''
                elif devName and devName in self._default_modules['devName']:
                    module_name = self._default_modules['devName'][devName]
                    module_path = ''

            if module_name:
                is_default_class = False
            else:
                is_default_class = True

            if not is_default_class:
                if path:
                    module_path = path
        
                if module_path:
                    if not quiet:
                        print 'Using the path {module_path} for {module_name}'.format( \
                               module_path=module_path, module_name=module_name)
                else:
                    module_path = self._default_modules['path']
                    
                det_dict['module']['path'] = module_path

                new_class = get_module(module_name, module_path, reload=True)
#                import_module(module_name, module_path)
#                try:
#                    new_class =  getattr(globals()[module_name],module_name)
#                except:
#                    new_class =  getattr(globals()[module_name],module_name.capitalize())
                
                det_dict['module']['dict'] = [attr for attr in new_class.__dict__ \
                                              if not attr.startswith('_')]

                if not quiet:
                    print 'Loading {alias} as {new_class} from {module_path}'.format(
                           alias=alias,new_class=new_class,module_path=module_path)
                
                nomodule = False
                self._detectors[alias] = new_class(self, alias, **kwargs)
                initialized = True

            if is_default_class:
                if not quiet:
                    print 'Loading {alias} as standard Detector class'.format(alias=alias)
                
                self._detectors[alias] = Detector(self, alias)
                initialized = True

        if initialized:
            self._init_dets.append(alias)

#    def add_plugin(self, cls, **kwargs):
#        self._plugins.update({cls.__name__: cls})

    def _add_dets(self, **kwargs):
        for alias, srcstr in kwargs.items():
            try:
                self.add_detector(srcstr, alias=alias, quiet=True)
            except Exception as err:
                print 'Cannot add {:}:  {:}'.format(alias, srcstr) 
                traceback.print_exc()

    def _get_config_file(self, path=None):
        if not path:
            path = '/reg/d/psdm/{:}/{:}/scratch/nc/'.format(self.instrument,self.experiment)

        if not os.path.isdir(path):
            os.mkdir(path)

        return '{:}/run{:04}.config'.format(path, int(self.data_source.run))

    def save_config(self, file_name=None, path=None, **kwargs):
        """
        Save DataSource configuration.
        
        Parameters
        ----------
        file_name : str
            Name of file
        path : str
            Path of file
        """
        if not file_name:
            file_name = self._get_config_file(path=path)

        pd.DataFrame.from_dict(self._device_sets).to_json(file_name)

    def load_config(self, file_name=None, path=None, **kwargs):
        """
        Load DataSource configuration.
        
        Parameters
        ----------
        file_name : str
            Name of file
        path : str
            Path of file
        """
        if not file_name:
            file_name = self._get_config_file(path=path)

        attrs = ['parameter', 'property', 'psplot', 'peak', 
                 'roi', 'projection', 'xarray']
 
        config = pd.read_json(file_name).to_dict()
        for alias, item in config.items():
            if alias in self._device_sets:
                for attr, config_dict in item.items():
                    if isinstance(config_dict, dict):
                        self._device_sets[alias][attr].update(**config_dict)
                    else:
                        self._device_sets[alias][attr] = config_dict
        

    def show_info(self, **kwargs):
        """
        Show DataSource information.
        """
        return self.configData.show_info(**kwargs)
    
    def __str__(self):
        return  str(self.data_source)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        if self.nevents:
            repr_str += ' {:} events'.format(self.nevents)
        print '< '+repr_str+' >'
        self.show_info()
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        if attr in self._ds_attrs:
            return getattr(self._ds, attr)()
        if attr in self._ds_funcs:
            return getattr(self._ds, attr)
        if attr in self._env_attrs:
            return getattr(self._ds.env(), attr)()
        
    def __dir__(self):
        all_attrs =  set(self._ds_attrs + 
                         self._ds_funcs + 
                         self._env_attrs +
                         self.__dict__.keys() + dir(DataSource))
        
        return list(sorted(all_attrs))


class Runs(object):
    """
    psana DataSource Run iterator from ds.runs().
    """
    def __init__(self, ds, **kwargs):
        self._ds_runs = []
        self._kwargs = kwargs
        self._ds = ds

    def __iter__(self):
        return self

    @property
    def current(self):
        return self._ds._current_run

    def next(self, **kwargs):
        """
        Returns
        -------
        iterator
            Run iterator
        
        See Also
        --------
        Run : class
            
        """
        self._ds._ds_run = self._ds._ds.runs().next()
        self._ds_runs.append(self._ds._ds_run)
        self._ds._irun +=1
        self._ds._istep = -1
        self._ds._ievent = -1
        self._ds._init_detectors()
        self._ds._current_run = Run(self._ds)

        return self._ds._current_run


class Run(object):
    """
    Python psana.Run class from psana.DataSource.runs().next().
    """
    _run_attrs = ['nsteps', 'times']
    _run_funcs = ['end', 'env']

    def __init__(self, ds, **kwargs):
        self._ds = ds

    @property
    def events(self):
        """RunEvents Iterator.

        Returns
        -------
        iterator
            Events in current run of DataSource.
        
        See Also
        --------
        RunEvents : class
        """
        return RunEvents(self._ds)

#    @property
#    def steps(self):
#        return RunSteps(self._ds)

    def __getattr__(self, attr):
        if attr in self._run_attrs:
            return getattr(self._ds._ds_run, attr)()
        if attr in self._run_funcs:
            return getattr(self._ds._ds_run, attr)
        
    def __dir__(self):
        all_attrs =  set(self._run_attrs +
                         self._run_funcs + 
                         self.__dict__.keys() + dir(Run))
        
        return list(sorted(all_attrs))


#class RunSteps(object):
#    """Step iterator from psana.DataSource.runs().steps().
#    """
#    def __init__(self, ds, **kwargs):
#        self._ds = ds
#        self._kwargs = kwargs
#        self._ds_steps = []
#        self._configSteps = []
#
#    def __iter__(self):
#        return self
#
#    def next(self):
#        try:
#            self._ds._ievent = -1
#            self._ds._istep +=1
#            self._ds._ds_step = self._ds._current_run.steps().next()
#            self._ds_steps.append(self._ds._ds_step)
#            self._ds._init_detectors()
#            return StepEvents(self._ds)
#        
#        except: 
#            raise StopIteration()


class RunEvents(object):
    """
    Event iterator from ds.runs() for indexed idx data 

    No support yet for multiple runs in a data_source
    """
    def __init__(self, ds, **kwargs):
        self._kwargs = kwargs
        self._ds = ds
        self.times = self._ds.runs.current.times 
        self._ds.nevents = len(self.times)

    def __iter__(self):
        return self

    @property
    def current(self):
        """
        Current event.
        
        See Also
        --------
        EvtDetectors
        """
        return EvtDetectors(self._ds, init=False)

    def next(self, evt_time=None, **kwargs):
        """Optionally pass either an integer for the event number in the data_source
           or a psana.EventTime time stamp to jump to an event.
        
        Parameters
        ----------
        evt_time : object or int
            psana.EventTime time stamp to jump to specific event,
            if int is supplied goto event number in DataSource (may not be exactly
            same event depending on how the data_source string is corresponding
            keywords to define the data_source is defined and also may differ
            for fast feedback and offline analysis environments.
        
        Returns
        -------
        EventDetectors : object
        """
        try:
            if evt_time is not None:
                if isinstance(evt_time, int):
                    self._ds._ievent = evt_time
                else:
                    self._ds._ievent = self.times.index(evt_time)
            else:
                self._ds._ievent += 1
            
            if self._ds._ievent >= len(self.times):
                raise StopIteration()
            else:
                evt = self._ds._ds_run.event(self.times[self._ds._ievent]) 
                self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
                self._ds._current_evt = evt
                self._ds._current_data = {}
                self._ds._current_evtData = {}

            return EvtDetectors(self._ds, **kwargs)

        except: 
            raise StopIteration()


class SmdEvents(object):
    """
    Event iterator for smd xtc data that iterates first over steps and then
    events in steps (to make sure configData is updated for each step since
    it is possible that it changes).
    """
    def __init__(self, ds, **kwargs):
        self._ds = ds

    @property
    def current(self):
        """Current event.
        """
        return EvtDetectors(self._ds, init=False)

    def __iter__(self):
        return self

    def next(self, evt_time=None, **kwargs):
        """
        Parameters
        ----------
        evt_time : object or int
            psana.EventTime time stamp (second, nanosecond, fiducial) to jump to 
            specific event,
            If int is supplied goto event number in DataSource (may not be exactly
            same event depending on how the data_source string is corresponding
            keywords to define the data_source is defined and also may differ
            for fast feedback and offline analysis environments.
        
        Returns
        -------
        EventDetectors object
            Returns next event in current step.  
            If at end of step goes to next step and returns first event.
        """
        try:
            return self._ds._current_step.next(evt_time=evt_time)
        except:
            try:
                self._ds.steps.next()
                return self._ds._current_step.next()
            except:
                raise StopIteration()


class Steps(object):
    """
    Step iterator from ds.steps().
    """
    def __init__(self, ds, **kwargs):
        self._ds = ds
        self._kwargs = kwargs
        self._ds_steps = []

    @property
    def current(self):
        """
        Current step.
        """
        return self._ds._current_step

    def __iter__(self):
        return self

    def next(self, **kwargs):
        """
        Step iteration method

        Returns
        -------
        StepEvents object
        """
        try:
            if self._ds._istep == self._ds._idx_run.nsteps()-1:
                raise StopIteration()
            else:
                self._ds._ievent = -1
                self._ds._istep +=1
                self._ds._ds_step = self._ds._ds.steps().next()
                self._ds_steps.append(self._ds._ds_step)
                self._ds._init_detectors()
                self._ds._current_step = StepEvents(self._ds)
                return self._ds._current_step

        except: 
            raise StopIteration()


class StepEvents(object):
    """
    Event iterator from ds.steps().events() 
    """
    def __init__(self, ds, **kwargs):
        self._kwargs = kwargs
        self._ds = ds

    @property
    def current(self):
        """Current event.
        """
        return EvtDetectors(self._ds, init=False)

    def __iter__(self):
        return self

    def next(self, evt_time=None, **kwargs):
        """
        Next event in step.  If no evt_time provided, the event loop will
        procede from the last event in the step regardless of which event 
        was previously jumped to.

        Optional Parameters
        ----------
        evt_time : object or int
            psana.EventTime time stamp (second, nanosecond, fiducial) to jump to 
            specific event,
            If int is supplied goto event number in DataSource (may not be exactly
            same event depending on how the data_source string is corresponding
            keywords to define the data_source is defined and also may differ
            for fast feedback and offline analysis environments.
 
        Returns
        -------
        EventDetectors object
            Returns next event in current step.  
        """
        if evt_time is not None:
            # Jump to the specified event
            try:
                if self._ds._istep >= 0:
                    # keep trak of event index to go back to step event loop
                    self._ds._ievent_last = self._ds._ievent
                    self._ds._istep_last = self._ds._istep
                    self._ds._istep = -1
                
                if evt_time.__class__.__name__ == 'EventTime':
                    # lookup event index from time tuple
                    ttup = (evt_time.seconds(), evt_time.nanoseconds(), evt_time.fiducial())
                    self._ds._ievent = self._ds._idx_times_tuple.index(ttup)
                elif isinstance(evt_time, tuple):
                    # optionally accept a time tuple (seconds, nanoseconds, fiducial)
                    self._ds._ievent = self._ds._idx_times_tuple.index(evt_time)
                    evt_time = self._ds._idx_times[self._ds._ievent]
                else:
                    # if an integer was passed jump to the appropriate time from 
                    # the list of run times -- i.e., psana.DataSource.runs().next().times()
                    self._ds._ievent = evt_time
                    evt_time = self._ds._idx_times[evt_time]

                #print self._ds._ievent, evt_time.seconds(), evt_time.nanoseconds()
                evt = self._ds._idx_run.event(evt_time) 
                    
                self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
                self._ds._current_evt = evt
                self._ds._current_data = {}
                self._ds._current_evtData = {}
            
            except:
                print evt_time, 'is not a valid event time'
        
        else:
            try:
                if self._ds._istep == -1:
                    # recover event and step index after previoiusly jumping to an event 
                    self._ds._ievent = self._ds._ievent_last
                    self._ds._istep = self._ds._istep_last
                
                self._ds._ievent += 1
                evt = self._ds._ds_step.events().next()
                self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
                self._ds._current_evt = evt 
                self._ds._current_data = {}
                self._ds._current_evtData = {}
            except:
                raise StopIteration()

        return EvtDetectors(self._ds, **kwargs)


class Events(object):
    """
    Event iterator
    """

    def __init__(self, ds, **kwargs):
        self._kwargs = kwargs
        self._ds = ds
        self._ds._init_detectors()

    @property
    def current(self):
        """
        Current event
        """
        return EvtDetectors(self._ds, init=False)

    def __iter__(self):
        return self

    def next(self, **kwargs):
        """
        Returns
        -------
        EventDetectors : object
            Returns next event in DataSource.  
        """
        try:
            self._ds._ievent += 1
            evt = self._ds._ds.events().next()
            self._ds._evt_keys, self._ds._evt_modules = get_keys(evt)
            self._ds._current_evt = evt 
            self._ds._current_data = {}
            self._ds._current_evtData = {}

        except:
            raise StopIteration()

        return EvtDetectors(self._ds, **kwargs)


class PsanaTypeList(object):
    """
    Python representation for lists of psana data objects.
    """

    def __init__(self, type_list):

        self._type_list = type_list
        typ_func = type_list[0]._typ_func
        module = typ_func.__module__.lstrip('psana.')
        type_name = typ_func.__class__.__name__
        info = psana_doc_info[module][type_name].copy()
        
        self._typ_func = typ_func
        self._values = {}
        self._attr_info = {}
        for attr, item in info.items():
            item['value'] = None

        attrs = [key for key in info.keys() if not key[0].isupper()]
        for attr in attrs:
            values = [getattr(item, attr) for item in self._type_list]

            try:
                if isinstance(values[0], np.ndarray):
                    values = np.array(values)
            except:
                pass
#                print module, type_name, info
#                print values

            if hasattr(values[0], '_typ_func'):
                vals = PsanaTypeList(values)
                for name, item in vals._attr_info.copy().items():
                    alias = attr+'_'+name
                    self._values[alias] = item['value']
                    self._attr_info[alias] = item.copy()
                    self._attr_info[alias]['attr'] = alias

            else:
                self._values[attr] = values
                self._attr_info[attr] = info[attr].copy()
                self._attr_info[attr]['value'] = values
                self._attr_info[attr]['attr'] = attr

        self._attrs = self._values.keys()

    @property
    def _all_values(self):
        """All values in a flattened dictionary.
        """
        avalues = {}
        items = sorted(self._values.items(), key = operator.itemgetter(0))
        for attr, val in items:
            if hasattr(val, '_all_values'):
                for a, v in val._all_values.items():
                    avalues[attr+'_'+a] = v
            else:
                avalues[attr] = val
        return avalues

    def show_info(self, prefix='', **kwargs):
        """Show a table of the attribute, value, unit and doc information
        """
        message = Message(quiet=True, **kwargs)
        items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
        for attr, item in items:
            if attr in self._attrs:
                alias = item.get('attr')
                str_repr = _repr_value(item.get('value'))
                unit = item.get('unit')
                doc = item.get('doc')
                if prefix:
                    alias = prefix+'_'+alias
                message('{:24s} {:>12} {:7} {:}'.format(alias, str_repr, unit, doc))

        return message

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self._values.get(attr)

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(PsanaTypeList))
        return list(sorted(all_attrs))


class PsanaTypeData(object):
    """
    Python representation of a psana data object (event or configStore data).
    """

    def __init__(self, typ_func, nolist=False):
        if typ_func:
            self._typ_func = typ_func
            module = typ_func.__module__.lstrip('psana.')
            type_name = typ_func.__class__.__name__
        else:
            type_name = None
        self._nolist = nolist

        if type_name in psana_doc_info[module]:
            self._info = psana_doc_info[module][type_name].copy()
            if psana_attrs.get(module,{}).get(type_name):
                self._attrs = [key for key in psana_attrs[module][type_name] if key in self._info.keys()] 
            else:
                self._attrs = [key for key in self._info.keys() if not key[0].isupper()]
            
            #print module,        
 
        else:
            self._attrs = [attr for attr in dir(typ_func) if not attr.startswith('_')]
            self._info = {}

        self._attr_info = {}
        for attr in self._attrs:
            self._attr_info[attr] = _get_typ_func_attr(typ_func, attr, nolist=nolist)
        
#        self._attr_info_new = {}
#        for attr in self._attrs_new:
#            self._attr_info_new[attr] = _get_typ_func_attr(typ_func, attr, nolist=nolist)

    @property
    def _values(self):
        """Dictionary of attributes: values. 
        """
        return {attr: self._attr_info[attr]['value'] for attr in self._attrs}

    @property
    def _all_values(self):
        """
        All values in a flattened dictionary.
        """
        avalues = {}
        items = sorted(self._values.items(), key = operator.itemgetter(0))
        for attr, val in items:
            if hasattr(val, '_all_values'):
                for a, v in val._all_values.items():
                    avalues[attr+'_'+a] = v
            else:
                avalues[attr] = val
        return avalues

    def show_info(self, prefix=None, **kwargs):
        """
        Show a table of the attribute, value, unit and doc information
        """
        message = Message(quiet=True, **kwargs)
        items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
        for attr, item in items:
            value = item.get('value')
            alias = item.get('attr')
            if prefix:
                alias = prefix+'_'+alias
            if hasattr(value, 'show_info'):
                value.show_info(prefix=alias, append=True)
            else:
                str_repr = _repr_value(item.get('value'))
                unit = item.get('unit')
                doc = item.get('doc')
                message('{:24s} {:>12} {:7} {:}'.format(alias, str_repr, unit, doc))

        return message

    def __str__(self):
        return '{:}.{:}.{:}'.format(self._typ_func.__class__.__module__,
                                    self._typ_func.__class__.__name__, 
                                    str(self._typ_func))

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self._attr_info[attr]['value']

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(PsanaTypeData))
        return list(sorted(all_attrs))


class PsanaSrcData(object):
    """
    Python represenation of psana data for a given detector source.
       
    Parameters
    ----------
    key_info : get_key_info(objclass) 
        for faster evt data access.
    """
    def __init__(self, objclass, srcstr, key_info=None, nolist=False):
        self._srcstr = srcstr
        if not key_info:
            key_info = get_key_info(objclass)

        self._types = {}
        self._type_attrs = {}
        self._keys = key_info.get(srcstr)
        if self._keys:
            for (typ, src, key) in self._keys:
                if key:
                    typ_func = objclass.get(*item)
                else:
                    typ_func = objclass.get(typ, src)

                module = typ_func.__module__.lstrip('psana.')
                type_name = typ_func.__class__.__name__
                type_alias = module+type_name+key 
                type_data = PsanaTypeData(typ_func, nolist=nolist)
                self._types[type_alias] = type_data 
                self._type_attrs.update({attr: type_alias for attr in type_data._attrs})
                #self._types[(typ,key)] = type_data 
                #self._type_attrs.update({attr: (typ,key) for attr in type_data._attrs})

    @property
    def _attrs(self):
        attrs = []
        for type_data in self._types.values():
            attrs.extend(type_data._attrs)

        return attrs

    @property
    def _attr_info(self):
        """Attribute information including the unit and doc information 
           and a str representation of the value for all data types.
        """
        attr_info = {}
        for type_data in self._types.values():
            attr_info.update(**type_data._attr_info)

        return attr_info

    @property
    def _values(self):
        """Dictionary of attributes: values for all data types.
        """
        values = {}
        for type_data in self._types.values():
            values.update(**type_data._values)

        return values

    @property
    def _all_values(self):
        """All values in a flattened dictionary.
        """
        values = {}
        for type_data in self._types.values():
            values.update(**type_data._all_values)

        return values

    def show_info(self, **kwargs):
        """Show a table of the attribute, value, unit and doc information
           for all data types of the given source.
        """
        message = Message(quiet=True, **kwargs)
        for type_data in self._types.values():
            type_data.show_info(append=True)

        return message

    def _get_type(self, typ):
        return self._types.get(typ)

    def __str__(self):
        return '{:}'.format(self._srcstr)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self))
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        item = self._type_attrs.get(attr)
        if item:
            return getattr(self._types.get(item), attr)
        
        if attr in self._types:
            return self._types.get(attr)

                   #
    def __dir__(self):
        all_attrs = set(self._type_attrs.keys() +
                        self._types.keys() + 
                        self.__dict__.keys() + dir(PsanaSrcData))
        return list(sorted(all_attrs))


class ConfigData(object):
    """
    Configuration Data representation of configStore within psana.DataSource.env object

    Parameters
    ----------
    ds : DataSource object
    """
    _configStore_attrs = ['get','put','keys']
    # Alias default provides way to keep aliases consistent for controls devices like the FEE_Spec
    _alias_defaults = {
            'BldInfo(FEE-SPEC0)':       'FEE_Spec',
            'BldInfo(NH2-SB1-IPM-01)':  'Nh2Sb1_Ipm1',
            'BldInfo(NH2-SB1-IPM-02)':  'Nh2Sb1_Ipm2',
            'BldInfo(MFX-BEAMMON-01)':  'MfxBeammon',
            }

    def __init__(self, ds):
        configStore = ds.env().configStore()
        if (hasattr(ds, 'data_source') and ds.data_source.monshmserver):
            self._monshmserver = ds.data_source.monshmserver
        else:
            self._monshmserver = None 
       
        self._ds = ds
        self._configStore = configStore
        self._key_info, self._modules = get_keys(configStore)

        # Build _config dictionary for each source
        self._config = {}
        for attr, keys in self._key_info.items():
            config = PsanaSrcData(self._configStore, attr, 
                                  key_info=self._key_info, nolist=True)
            self._config[attr] = config

        self._sources = {}
        #Setup Partition
        if not self._modules.get('Partition'):
            #print 'ERROR:  No Partition module in configStore data.'
            self._partition = {}
            self._srcAlias = {}
            for srcstr, item in self._config.items():
                if srcstr[0:7] in ['BldInfo', 'DetInfo']:
                    alias = srcstr[8:-1]
                    alias = re.sub('-|:|\.| ','_', alias)
                    src = item._keys[0][1] 
                    self._partition[srcstr] = {
                                               #'alias': alias, 
                                               'group': 0, 
                                               'src': src}

                    self._srcAlias[alias] = (src, 0)

                self._bldMask = 0
                self._ipAddrpartition = 0 
                self._readoutGroup = {0: {'eventCodes': [], 'srcs': []}}

        elif len(self._modules['Partition']) != 1:
            print 'ERROR:  More than one Partition config type in configStore data.'
            return
        else:
            #Build _partition _srcAlias _readoutGroup dictionaries based on Partition configStore data. 
            type_name = self._modules.get('Partition').keys()[0]
            if len(self._modules['Partition'][type_name]) == 1:
                typ, src, key = self._modules['Partition'][type_name][0]
                srcstr = str(src)
                config = self._config[srcstr]
                self.Partition = config
            else:
                print 'ERROR:  More that one Partition module in configStore data.'
                print '       ', self._modules['Partition'][type_name]
                return

    # to convert ipAddr int to address 
    # import socket, struct
    # s = key.src()
    # socket.inet_ntoa(struct.pack('!L',s.ipAddr()))

            self._ipAddrPartition = src.ipAddr()
            self._bldMask = config.bldMask
            self._readoutGroup = {group: {'srcs': [], 'eventCodes': []} \
                                  for group in set(config.sources.group)}
            self._partition = {str(src): {'group': config.sources.group[i], 'src': src} \
                               for i, src in enumerate(config.sources.src)}

            self._srcAlias = {}
            if self._modules.get('Alias'):
                for type_name, keys in self._modules['Alias'].items():
                    for typ, src, key in keys:
                        srcstr = str(src)
                        config = self._config[srcstr]
                        ipAddr = src.ipAddr()
                        for i, source in enumerate(config.srcAlias.src):
                            alias = config.srcAlias.aliasName[i]
                            self._srcAlias[alias] = (source, ipAddr)

        self._aliases = {}
        for alias, item in self._srcAlias.items():
            src = item[0]
            ipAddr = item[1]
            srcstr = str(src)
            alias = re.sub('-|:|\.| ','_', alias)
            group = None
            if srcstr in self._partition:
                self._partition[srcstr]['alias'] = alias
                if srcstr.find('NoDetector') == -1:
                    self._aliases[alias] = srcstr
                
                group = self._partition[srcstr].get('group', -1)
            
            elif ipAddr != self._ipAddrPartition or self._monshmserver:
                if self._monshmserver:
                    # add data sources not in partition for live data
                    group = -2
                else:
                    # add data sources not in partition that come from recording nodes
                    group = -1

                self._partition[srcstr] = {'src': src, 'group': group, 'alias': alias}
                self._aliases[alias] = srcstr
                if group not in self._readoutGroup:
                    self._readoutGroup[group] = {'srcs': [], 'eventCodes': []}

                self._sources[srcstr] = {'group': group, 'alias': alias}
            
            if group:
                self._readoutGroup[group]['srcs'].append(srcstr)
            #else:
            #    print 'No group for', srcstr

        # Determine data sources and update aliases
        for srcstr, item in self._partition.items():
            if not item.get('alias'):
                if srcstr in self._alias_defaults:
                    alias = self._alias_defaults.get(srcstr)
                else:
                    try:
                        alias = srcstr.split('Info(')[1].rstrip(')')
                    except:
                        alias = srcstr
                
                alias = re.sub('-|:|\.| ','_',alias)
                item['alias'] = alias
                self._aliases[alias] = srcstr

            if 'NoDetector' not in srcstr and 'NoDevice' not in srcstr:
                # sources not recorded have group None
                # only include these devices for shared memory
                if srcstr not in self._sources:
                    self._sources[srcstr] = {}
                self._sources[srcstr].update(**item)

        # Make dictionary of src: alias for sources with config objects 
        self._config_srcs = {}
        for attr, item in self._sources.items():
            config = self._config.get(attr)
            if config:
                self._config_srcs[item['alias']] = attr
    
        self._output_maps = {}
        self._evr_pulses = {}
        self._eventcodes = {}

        IOCconfig_type = None
        config_type = None
        for type_name in self._modules['EvrData'].keys():
            if type_name.startswith('IOConfig'):
                IOCconfig_type = type_name
                self._IOCconfig_type = type_name
            elif type_name.startswith('Config'):
                config_type = type_name

        if IOCconfig_type:
            # get eventcodes and combine output_map info from all EvrData config keys
            map_attrs = ['map', 'conn_id', 'module', 'value', 'source_id']
            for typ, src, key in self._modules['EvrData'][config_type]:
                srcstr = str(src)
                config = self._config[srcstr]
                for eventcode in config.eventcodes._type_list:
                    self._eventcodes.update({eventcode.code: eventcode._values})
                    if eventcode.isReadout:
                        group = eventcode.readoutGroup
                        if group not in self._readoutGroup:
                            self._readoutGroup[group] = {'srcs': [], 'eventCodes': []}
                        self._readoutGroup[group]['eventCodes'].append(eventcode.code)

                for output_map in config.output_maps._type_list:
                    map_key = (output_map.module,output_map.conn_id)
                    if output_map.source == 'Pulse':
                        pulse_id = output_map.source_id
                        pulse = config.pulses._type_list[pulse_id]
                        evr_info = { 'evr_width': pulse.width*pulse.prescale/119.e6, 
                                     'evr_delay': pulse.delay*pulse.prescale/119.e6, 
                                     'evr_polarity': pulse.polarity}
                    else:
                        pulse_id = None
                        pulse = None
                        evr_info = {'evr_width': None, 'evr_delay': None, 'evr_polarity': None}

                    self._output_maps[map_key] = {attr: getattr(output_map,attr) for attr in map_attrs} 
                    self._output_maps[map_key].update(**evr_info) 

            # Assign evr info to the appropriate sources
            if len(self._modules['EvrData'][IOCconfig_type]) > 1:
                print 'WARNING: More than one EvrData.{:} objects'.format(IOCconfig_type)

            IOCconfig_type = self._IOCconfig_type
            typ, src, key = self._modules['EvrData'][IOCconfig_type][0]
            srcstr = str(src)
            config = self._config[srcstr]
            if config._values['channels']:
                for ch in config._values['channels']._type_list:
                    map_key = (ch.output.module, ch.output.conn_id)
                    for i in range(ch.ninfo):
                        src = ch.infos[i]
                        srcstr = str(src)
                        self._sources[srcstr]['map_key'] = map_key
                        for attr in ['evr_width', 'evr_delay', 'evr_polarity']:
                            self._sources[srcstr][attr] = self._output_maps[map_key][attr]

            for group, item in self._readoutGroup.items():
                if item['eventCodes']:
                    for srcstr in item['srcs']: 
                        if srcstr in self._sources:
                            self._sources[srcstr]['eventCode'] = item['eventCodes'][0]

        # Get control data
        if self._modules.get('ControlData'):
            type_name, keys = self._modules['ControlData'].items()[0]
            typ, src, key = keys[0]
            config = self._config[str(src)]
            self._controlData = config._values
            self.ControlData = config

        if self._modules.get('SmlData'):
            type_name, keys = self._modules['SmlData'].items()[0]
            typ, src, key = keys[0]
            config = self._config[str(src)]
            self._smlData = config._values

    @property
    def Sources(self):
        """
        Source information including evr config.
        
        Returns
        -------
        ConfigSources object
        
        """
        return ConfigSources(self)

    @property
    def ScanData(self):
        """
        Scan configuration from steps ControlData.  
        May take several seconds to load the first time.
        Only relevant for smd data.
        
        Returns
        -------
        ScanData object
        """
        #if self._ds.data_source.monshmserver is not None:
        if not self._ds.data_source.smd:
            return None

        if self._ds._scanData is None:
            self._ds._scanData = ScanData(self._ds)

        return self._ds._scanData

    def show_info(self, **kwargs):
        """Show Detector Source information.
        """
        message = Message(quiet=True, **kwargs)
        message('-'*80)
        message('Source Information:')
        message('-'*18)
        self.Sources.show_info(append=True)
        
        return message

    def show_all(self, **kwargs):
        """Show Detector Source and ScanData information.
        """
        message = Message(quiet=True, **kwargs)
        message('-'*80)
        message('Source Information:')
        message('-'*18)
        self.Sources.show_info(append=True)
        message('') 
        message('-'*80)
        message('Scan Data:')
        message('-'*18)
        self.ScanData.show_info(append=True)

        return message

    def __str__(self):
        return  'ConfigData: '+str(self._ds.data_source)

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__,str(self._ds.data_source))
        print '< '+repr_str+' >'
        print self.Sources.show_info()
        return '< '+repr_str+' >'
    
    def __getattr__(self, attr):
        if attr in self._config_srcs:
            return self._config[self._config_srcs[attr]]

        if attr in self._configStore_attrs:
            return getattr(self._configStore, attr)
        
    def __dir__(self):
        all_attrs = set(self._configStore_attrs +
                        self._config_srcs.keys() + 
                        self.__dict__.keys() + dir(ConfigData))
        return list(sorted(all_attrs))


class EvtDetectors(object):
    """
    Psana tab accessible event detectors.
    All detectors in Partition or defined in any configStore Alias object 
    (i.e., recording nodes as well as daq) return the relevant attributes of 
    a PyDetector object for that src, but only the sources in the evt.keys()
    show up in the ipython tab accessible dir.
    
    Preserves get, keys and run method of items in psana events iterators.
    
    Parameters
    ----------
    ds : DataSource object
    """

    _init_attrs = ['get', 'keys'] #  'run' depreciated
    _event_attrs = ['EventId', 'Evr', 'L3T']

    def __init__(self, ds, publish=True, init=True): 
        self._ds = ds
        if init:
            self._init(publish=publish)

    def _init(self, publish=True):
        if publish:
            psmon_publish(self)
 
    @property
    def EventId(self):
        """
        EventId object
        """
        return EventId(self._ds._current_evt)

    @property
    def _attrs(self):
        """
        List of detector names in current evt data.
        """
        return [alias for alias, srcstr in self._ds._aliases.items() \
                                        if srcstr in self._ds._evt_keys]

    @property
    def _dets(self):
        """
        Dictionary of detectors.
        
        Returns
        -------
        DataSource._detectors dict
        """
        return self._ds._detectors

    @property
    def Evr(self):
        """
        Master evr from psana evt data.
        
        Returns
        -------
        EvrData object
        """
        if 'EvrData' in self._ds._evt_modules:
            return EvrData(self._ds)
        else:
            return EvrNullData(self._ds)

    @property
    def L3T(self):
        """
        L3T Level 3 trigger.
        
        Returns
        -------
        L3Tdata object
        """
        if 'L3T' in self._ds._evt_modules:
            return L3Tdata(self._ds)
        else:
            return L3Ttrue(self._ds)

    def next(self, *args, **kwargs):
        """
        Returns
        -------
        EvtDetectors : object
            Next event in DataSource (behavior depends on if smd, idx options used in data_source)
        """
        evt = self._ds.events.next(*args, **kwargs)
        return evt

    def __iter__(self):
        return self

    def __str__(self):
        return  '{:}, Run {:}, Step {:}, Event {:}, {:}, {:}'.format(self._ds.data_source.exp, 
                self._ds.data_source.run, self._ds._istep, self._ds._ievent, 
                str(self.EventId), str(self.Evr))

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__, str(self))
        return '< '+repr_str+' >'

    def __getattr__(self, attr):
        if attr in self._ds._detectors:
            return self._ds._detectors[attr]
        
        if attr in self._init_attrs:
            return getattr(self._ds._current_evt, attr)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self._init_attrs +
                         self.__dict__.keys() + dir(EvtDetectors))
        
        return list(sorted(all_attrs))


class L3Ttrue(object):
    """
    L3 Trigger default if no L3 Trigger data is in DataSource.
    Typically only used for older data where no L3 Trigger data was generated.
    """

    def __init__(self, ds):

        self._ds = ds
        self._attr_info = {'result': {'attr': 'result',
                                      'doc':  'No L3T set',
                                      'unit': '',
                                      'value': True}}

        self._attrs = self._attr_info.keys()

    @property
    def _values(self):
        """
        Dictionary of attributes: values. 
        """
        return {attr: self._attr_info[attr]['value'] for attr in self._attrs}

    def show_info(self, **kwargs):
        """
        Show a table of the attribute, value, unit and doc information
        """
        message = Message(**kwargs)
        items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
        for attr, item in items:
            value = item.get('value')
            if hasattr(value, 'show_info'):
                value.show_info(prefix=attr, append=True)
            else:
                item['str'] = _repr_value(value)
                message('{attr:24s} {str:>12} {unit:7} {doc:}'.format(**item))

        return message

    def __str__(self):
        return str(self.result)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self._attr_info[attr]['value']

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(L3Ttrue))
        return list(sorted(all_attrs))


class L3Tdata(PsanaTypeData):
    """
    L3 Trigger data
    """
    def __init__(self, ds):

        self._typ, self._src, key = ds._evt_modules['L3T'].values()[0][0]
        typ_func = ds._current_evt.get(self._typ,self._src)
        PsanaTypeData.__init__(self, typ_func)

    def __str__(self):
        return str(self.result)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))


class ConfigSources(object):
    """
    Configuration Sources

    Parameters
    ----------
    configData : ConfigData object

    """

    def __init__(self, configData):
        self._sources = configData._sources
        self._aliases = {item['alias']: src for src, item in self._sources.items()}
        self._cfg_srcs = configData._config_srcs.values()
        self._repr = str(configData._ds) 

    def show_info(self, **kwargs):
        message = Message(quiet=True, **kwargs)
        message('*Detectors in group 0 are "BLD" data recorded at 120 Hz on event code 40')
        if self._monshmserver:
            message('*Detectors listed as Monitored are not being recorded (group -2).')
        else:
            message('*Detectors listed as Controls are controls devices with unknown event code (but likely 40).')
        message('')
        header =  '{:22} {:>8} {:>13} {:>5} {:>5} {:12} {:12} {:26}'.format('Alias', 'Group', 
                 'Rate', 'Code', 'Pol.', 'Delay [s]', 'Width [s]', 'Source') 
        message(header)
        message('-'*(len(header)+10))
        data_srcs = {item['alias']: s for s,item in self._sources.items() \
                       if s in self._cfg_srcs or s.startswith('Bld')}
        
        for alias, srcstr in sorted(data_srcs.items(), key = operator.itemgetter(0)):
            item = self._sources.get(srcstr,{})

            polarity = item.get('evr_polarity', '')
            # Epics convention used -- has it always been this?
            # I was previously using the opposite convetion here
            if polarity == 0:
                polarity = 'Pos'
            elif polarity == 1:
                polarity = 'Neg'

            delay = item.get('evr_delay', '')
            if delay:
                delay = '{:11.9f}'.format(delay)

            width = item.get('evr_width', '')
            if width:
                width = '{:11.9f}'.format(width)

            group = item.get('group')
            if group == -1:
                group = 'Controls'
            elif group == -2:
                group = 'Monitor'

            if group == 0:
                eventCode = 40
            else:
                eventCode = item.get('eventCode', '')

            rate = _eventCodes_rate.get(eventCode, '')

            message('{:22} {:>8} {:>13} {:>5} {:>5} {:12} {:12} {:40}'.format(alias, 
                   group, rate, eventCode, polarity, delay, width, srcstr))

        return message

    def __str__(self):
        return  self._repr

    def __repr__(self):
        repr_str = '{:}: {:}'.format(self.__class__.__name__, self._repr)
        return '< '+repr_str+' >'
 
    def __getattr__(self, attr):
        if attr in self._aliases:
            srcstr = self._aliases[attr]
            return SourceData(self._sources[srcstr])

    def __dir__(self):
        all_attrs =  set(self._aliases.keys() +
                         self.__dict__.keys() + dir(ConfigSources))
        
        return list(sorted(all_attrs))


class SourceData(object):
    """
    Source information for a daq device.

    Parameters
    ----------
    source : str
        Source name

    Attributes
    ----------
    evr_width : float
        Detector evr trigger width ['s']
    evr_delay : float
        Detector evr trigger delay ['s']
    evr_polarity : bool
        Detector evr trigger polarity
    group: int
        Daq evr group
    map_key: int tuple
        Evr configuation map key (card,channel)
    eventCode: int
        Evr event code
    """

    _units = {'evr_width': 's',
              'evr_delay': 's'}

    _doc = {'evr_width': 'Evr trigger width',
            'evr_delay': 'Evr trigger delay',
            'evr_polarity': 'Evr trigger polarity',
            'group': 'Evr group',
            'map_key': 'Evr configuation map key (card,channel)',
            'eventCode': 'Evr event code',
            }

    def __init__(self, source):
        self._source = source

    def show_info(self, **kwargs):
        message = Message(quiet=True, **kwargs)
        for attr in self._source:
            val = self._source[attr]
            if attr in self._units:
                val = '{:10.9f}'.format(val)
            item = [attr, val, self._units.get(attr, ''), self._doc.get(attr, '')]
            message('{:22} {:>12} {:3} {:40}'.format(*item))

        return message

    def __str__(self):
        return '{:} = {:}'.format(self._source.get('alias'), self._source.get('src'))

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))

    def __getattr__(self, attr):
        if attr in self._source:
            return self._source[attr]

    def __dir__(self):
        all_attrs =  set(self._source.keys()+
                         self.__dict__.keys() + dir(SourceData))
        
        return list(sorted(all_attrs))


class EvrData(PsanaTypeData):
    """
    Evr eventCode information for current event in DataSource 

    Parameters
    ----------
    ds : DataSource object
    """

    def __init__(self, ds):

        self._typ, self._src, key = ds._evt_modules['EvrData'].values()[0][0]
        typ_func = ds._current_evt.get(self._typ,self._src)
        PsanaTypeData.__init__(self, typ_func)
        self.eventCodes = self.fifoEvents.eventCode

    def _present(self, eventCode):
        """Return True if the eventCode is present.
        """
        try:
            pres = self._typ_func.present(eventCode)
            if pres:
                return True
            else:
                return False
        except:
            return False

    def present(self, *args):
        """
        Check if the event has specified event code.
        Multiple event codes can be tested.
        
        Example
        -------
        
        Assume: 
            self.eventCodes = [41, 140]
        Then:
            self.present(41, 140) = True
            self.present(42, 140) = Flase
            
        To check if an event code is not present use a negative number:
            self.present(-41) = False
            self.present(-41, 140) = False
            self.present(-42) = True
            self.present(-42, 140) = True
            self.present(-42, 41, 140) = True
        """
        if args[0] is None:
            return True

        if len(args) == 1:
            if isinstance(args[0], list):
                eventCodes = {arg for arg in args[0]}
            else:
                eventCodes = args
        else:
            eventCodes = args

        for eventCode in eventCodes:
            if (eventCode > 0 and not self._present(eventCode)) \
                    or (eventCode < 0 and self._present(abs(eventCode))):
                return False

        return True

    def show_table(self, **kwargs):
        """Show table of event codes present'
        """
        message = Message(quiet=True, **kwargs)
        ecs = self.fifoEvents
        message('{:>8} {:>10} {:>10}'.format('Code','TS_high', 'TS_low'))
        for i in range(self.numFifoEvents):
            message('{:8} {:10} {:10}'.format(ecs.eventCode[i], 
                            ecs.timestampHigh[i], ecs.timestampLow[i]))
        return message

    def __str__(self):
        try:
            eventCodeStr = '{:}'.format(self.eventCodes)
        except:
            eventCodeStr = ''
        
        return eventCodeStr

class EvrNullData(object):
    """
    Evr data class when no EvrData type is in event keys.
    Occurs for controls cameras with no other daq data present.
    """

    def __init__(self, ds):
        self.eventCodes = []

    def __str__(self):
        return ''


class EventId(object):
    """
    Time stamp information from psana EventId. 
    """

    _attrs = ['fiducials', 'idxtime', 'run', 'ticks', 'time', 'vector']
    _properties = ['datetime64', 'EventTime', 'timef64', 'nsec', 'sec']

    def __init__(self, evt):

        self._EventId = evt.get(psana.EventId)

    @property
    def datetime64(self):
        """
        NumPy datetime64 representation of EventTime.
        
        References 
        ----------

        http://docs.scipy.org/doc/numpy/reference/arrays.datetime.html
        
        """
        return np.datetime64(int(self.sec*1e9+self.nsec), 'ns')

    @property
    def EventTime(self):
        """
        psana.EventTime for use in indexed idx xtc files.
        """
        return psana.EventTime(int((self.sec<<32)|self.nsec), self.fiducials)

    @property
    def timef64(self):
        """
        Event time represented as float64
        """
        return np.float64(self.sec)+np.float64(self.nsec)/1.e9 

    @property
    def nsec(self):
        """
        Nanosecond part of event time.
        """
        return self.time[1]

    @property
    def sec(self):
        """
        Second part of event time.
        """
        return self.time[0]

    def show_info(self, **kwargs):
        """
        Returns
        -------
        Message object
            Time stamp information for event 
        """
        message = Message(quiet=True, **kwargs)
        message(self.__repr__())
        for attr in self._attrs:
            if attr != 'idxtime': 
                message('{:18s} {:>12}'.format(attr, getattr(self, attr)))

        return message

    def __str__(self):
        try:
            EventTimeStr = time.strftime('%H:%M:%S',
                    time.localtime(self.time[0]))
            EventTimeStr += '.{:04}'.format(int(self.time[1]/1e5))
        except:
            EventTimeStr = 'NA'

        return '{:}'.format(EventTimeStr)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(self._EventId, attr)()

    def __dir__(self):
        all_attrs =  set(self._attrs+
                         self.__dict__.keys() + dir(EventId))
        
        return list(sorted(all_attrs))


class Detector(object):
    """
    Includes epicsData, configData, evrConfig info 
    Uses full ds in order to be able to access epicsData info on
    an event basis.
    """
    #import Detector as psanaDetector
    # dict of detectors in psana.DetectorTypes.detectors
   
    _tabclass = 'evtData'
    _calib_class = None
    _det_class = None
    _ds = None
    _alias = ''
    src = ''
    _pydet = None
    _pydet_name = None
    _init = False
    _xarray_init = False

    def __init__(self, ds, alias, verbose=False, **kwargs):
        """
        Initialize a psana Detector class for a given detector alias.
        Provides the attributes of the PyDetector functions for the current 
        event if applicable.  Otherwise provides the attributes from the
        raw data in the psana event keys for the given detector.
        """

        self._alias = alias
        self._ds = ds
        self.src = ds._aliases.get(alias)
        if not self._xarray_info:
            self._xarray_info.update({'coords': {}, 'dims': {}, 'attrs': {}})
        
        self._source = ds.configData._sources.get(self.src)

        if self.src:
            if verbose:
                print 'Adding Detector: {:20} {:40}'.format(alias, psana.Source(self.src))
        
        else:
            print 'ERROR No Detector with alias {:20}'.format(alias)
            return

        self._srcstr = str(self.src)
        #self._srcname = self._srcstr.split('(')[1].split(')')[0]
        srcname = self._det_config['srcname']
 
        try:
            self._pydet = psana.Detector(srcname, ds._ds.env())
            self._pydet_name = self._pydet.__class__.__name__
        except:
            pass

        _pydet_dict = {
                'AreaDetector':  {'det_class': ImageData,
                                  'calib_class': ImageCalibData},
                'WFDetector':    {'det_class': WaveformData,
                                  'calib_class': WaveformCalibData},
                'IpimbDetector': {'det_class': IpimbData,
                                  'calib_class': None},
                }

        item = _pydet_dict.get(self._pydet_name)
        if item:
            self._det_class = item.get('det_class')
            self._calib_class = item.get('calib_class')
            self._tabclass = 'detector'

        self._init = True

    @property
    def add(self):
        """
        Add data processing methods.

        See Also
        --------
        AddOn : class
            Methods to add parameters, properties, and reduction/proccesing of data 
            with roi, projection, histogram methods.
        """
        return AddOn(self._ds, self._alias)
   
    @property
    def _det_config(self):
        """
        Detector configuration

        See Also
        --------
        _device_sets : dict
            Dictionary of detector devices in DataSource object.
        """
        return self._ds._device_sets.get(self._alias)

    @property
    def _xarray_info(self):
        """
        Dictionary of information to build xarray data summaries.
        """
        return self._det_config['xarray']

    def _update_xarray_info(self):
        """
        Update default xarray information
        """
        # attrs -- not valid yet for bld but should fix this to avoid try/except here
        self._xarray_init = True
        try:
            attrs = {attr: item for attr, item in self.configData._all_values.items() \
                if np.product(np.shape(item)) <= 17}
        except:
            attrs = {}

        self._xarray_info['attrs'].update(**attrs)

        # xarray dims
        if self.src == 'BldInfo(FEE-SPEC0)':
            dims_dict = {attr: ([], ()) for attr in ['integral', 'npeaks']}
            dims_dict['hproj'] = (['X'], self.hproj.shape)

        elif self.src == 'DetInfo(XrayTransportDiagnostic.0:Opal1000.0)':
            dims_dict = {'data16': (['X', 'Y'], self.evtData.data16.shape)}

        elif self._det_class == WaveformData:
            if self._pydet.dettype == 17:
                dims_dict = {'waveform': (['ch', 't'], (4, self.configData.numberOfSamples))} 
            else:
                dims_dict = {
                        'waveform':  (['ch', 't'], 
                            (self.configData.nbrChannels, self.configData.horiz.nbrSamples)),
                        }

        elif self._det_class == IpimbData:
            dims_dict = {
                    'sum':      ([], ()),
                    'xpos':     ([], ()),
                    'ypos':     ([], ()),
                    'channel':  (['ch'], (4,)),
                    }

        elif self._det_class == ImageData:
            if self.calibData.ndim == 3:
                raw_dims = (['sensor', 'row', 'column'], self.calibData.shape)
                image_shape = (self.calibData.image_xaxis.size, self.calibData.image_yaxis.size)
                image_dims = (['X', 'Y'], image_shape) 
                dims_dict = {
                    'image':     image_dims,
                    'calib':     raw_dims,
#                    'raw':       raw_dims,
                    }
           # # temporary fix for Opal2000, Opal4000 and Opa8000
           # elif self._pydet.dettype in [7,8,9]:
           #     dims_dict = {'raw': (['X', 'Y'], self.evtData.data16.shape)}

            else:
                if self.calibData.image_xaxis is not None and self.calibData.image_xaxis.size > 0:
                    raw_dims = (['X', 'Y'], self.calibData.shape)
                    image_shape = (len(self.calibData.image_xaxis),len(self.calibData.image_yaxis))
                    image_dims = (['X', 'Y'], image_shape)
                    #dims_dict = {'calib':     image_dims}
                    dims_dict = {'raw':     image_dims}
                else:
                    dims_dict = {'raw': (['X', 'Y'], self.evtData.data16.shape)}

        # temporary fix for Quartz camera not in PyDetector class
        elif self._pydet is not None and hasattr(self._pydet, 'dettype') \
                and self._pydet.dettype == 18:
            try:
                dims_dict = {'data8': (['X', 'Y'], self.data8.shape)}
            except:
                print str(self), 'Not valid data8'
        
        else:
            dims_dict = {}
            for attr, val in self.evtData._all_values.items():
                npval = np.array(val)
                if npval.size > 1:
                    dims_dict[attr] = (['d{:}_{:}'.format(i,a) for i,a in enumerate(npval.shape)], npval.shape)
                else:
                    info = self.evtData._attr_info.get(attr)
                    if info:
                        xattrs = {a: b for a, b in info.items() if a in ['doc','unit']}
                    else:
                        xattrs = {}
                    dims_dict[attr] = ([], (), xattrs)

#            dims_dict = {attr: ([], ()) for attr in self.evtData._all_values}
                    
        self._xarray_info['dims'].update(**dims_dict)

        # coords
        if self._det_class == WaveformData:
            if self._pydet.dettype == 17:
                coords_dict = {
                        't': np.arange(self.configData.numberOfSamples) 
                        }
            else:
                coords_dict = {
                        't': np.arange(self.configData.horiz.nbrSamples) \
                                *self.configData.horiz.sampInterval \
                                +self.configData.horiz.delayTime
                        }

        # temporary fix for Opal2000, Opal4000 and Opa8000
        elif self._det_class == ImageData:
            if self.calibData.ndim == 3:
                raw_dims = (['sensor', 'row', 'column'], self.calibData.shape)
                attrs = ['areas', 'coords_x', 'coords_y', 'coords_z', 
                         'gain', 'indexes_x', 'indexes_y', 'pedestals', 'rms'
                         'image_xaxis', 'image_yaxis']
                coords_dict = {
                        'X': self.calibData.image_xaxis,
                        'Y': self.calibData.image_yaxis
                        }

            elif self.calibData.ndim == 2 and self.calibData.shape[0] > 0 and self.calib is None:
                attrs = []
                coords_shape = self.raw.shape
                coords_dict = {'X': np.arange(coords_shape[0]), 
                               'Y': np.arange(coords_shape[1])}

            elif self.calibData.ndim == 2 and  self.calibData.shape[0] > 0:
                raw_dims = (['X', 'Y'], self.calibData.shape)
                attrs = []
                coords_dict = {
                        'X': self.calibData.image_xaxis,
                        'Y': self.calibData.image_yaxis
                        }
            else:
                coords_dict = {}
                attrs = []

            for attr in attrs:
                val = getattr(self.calibData, attr)
                if val is not None:
                    coords_dict[attr] = (raw_dims[0], val)
        
        else:
            coords_dict = {}

        self._xarray_info['coords'].update(**coords_dict)

    def _add_xarray_evtData(self, attrs=[]):
        """
        Add evtData xarray information.
        """
        dims_dict = {}
        for attr in attrs:
            if attr in self.evtData._all_values:
                val = self.evtData._all_values.get(attr)
                npval = np.array(val)
                if npval.size > 1:
                    dims_dict[attr] = (['d{:}_{:}'.format(i,a) for i,a in enumerate(npval.shape)], npval.shape)
                else:
                    info = self.evtData._attr_info.get(attr)
                    if info:
                        xattrs = {a: b for a, b in info.items() if a in ['doc','unit']}
                    else:
                        xattrs = {}
                    dims_dict[attr] = ([], (), xattrs)

        self._xarray_info['dims'].update(**dims_dict)


    @property
    def _attrs(self):
        """
        Attributes of psana.Detector functions if relevant, and otherwise
        attributes of raw psana event keys for the given detector.
        """
        if self._tabclass:
            tabclass = getattr(self, self._tabclass)
            if hasattr(tabclass, '_attrs'):
                return tabclass._attrs

        return []

    def next(self, **kwargs):
        """
        Return next event that contains the Detector in the event data.
        """
        in_keys = False
        while not in_keys:
            evt = self._ds.events.next(init=False, **kwargs) 
            in_keys = self._alias in evt._attrs

        evt._init()
        return getattr(evt, self._alias)
 
    def __iter__(self):
        return self

    def monitor(self, nevents=-1, sleep=0.2):
        """
        Monitor detector attributes continuously with show_info function.
        """ 
        ievent = nevents
        while ievent != 0:
            try:
                self.next()
                try:
                    print self.show_info()
                except:
                    pass
                
                if ievent < nevents and sleep:
                    time.sleep(sleep)

                ievent -= 1

            except KeyboardInterrupt:
                ievent = 0

    def _show_user_info(self, **kwargs):
        """
        Show user defined information from AddOn methods.
        """
        message = Message(quiet=True, **kwargs)
#        if self._det_config.get('module') and self._det_config['module'].get('dict'):
#            message('-'*80)
#            message('Class Properties:')
#            message('-'*18)
#            for attr in self._det_config['module'].get('dict', []):
#                val = getattr(self, attr)
#                try:
#                    val = val()
#                except:
#                    pass
#                
#                strval = _repr_value(val)
#                fdict = {'attr': attr, 'str': strval, 'unit': '', 'doc': ''}
#                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))

        if self._det_config['projection']:
            message('-'*80)
            message('User Defined Projections:')
            message('-'*18)
            for attr, item in self._det_config['projection'].items():
                fdict = item.copy()
                val = getattr(self, attr)
                try:
                    val = val()
                except:
                    pass
 
                strval = _repr_value(val)
                fdict.update({'attr': attr, 'str': strval})
                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
 
        if self._det_config['histogram']:
            message('-'*80)
            message('User Defined Histograms:')
            message('-'*18)
            for attr, item in self._det_config['histogram'].items():
                fdict = item.copy()
                val = getattr(self, attr)
                try:
                    val = val()
                except:
                    pass
 
                strval = _repr_value(val)
                fdict.update({'attr': attr, 'str': strval})
                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
 
        if self._det_config['count']:
            message('-'*80)
            message('Detector Counts:')
            message('-'*18)
            for attr, item in self._det_config['count'].items():
                fdict = item.copy()
                val = getattr(self, attr)
                strval = _repr_value(val)
                fdict.update({'attr': attr, 'str': strval})
                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
 
        if self._det_config['parameter']:
            message('-'*80)
            message('User Defined Parameters:')
            message('-'*18)
            for attr, val in self._det_config['parameter'].items():
                strval = _repr_value(val)
                fdict = {'attr': attr, 'str': strval, 'unit': '', 'doc': ''}
                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
 
        if self._det_config['peak']:
            message('-'*80)
            message('User Defined 1D Peak Result:')
            message('-'*18)
            items = sorted(self._det_config['peak'].items(), key=operator.itemgetter(0))
            for attr, item in items:
                val = getattr(self, attr)
                if hasattr(val, 'mean') and val.size > 1:
                    strval = '<{:}>'.format(val.mean())
                else:
                    try:
                        strval = '{:10.5g}'.format(val)
                    except:
                        strval = str(val)

                doc = item.get('doc','')
                unit = item.get('unit','')
                fdict = {'attr': attr, 'str': strval, 'unit': unit, 'doc': doc}
                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
 
        if self._det_config['property']:
            message('-'*80)
            message('User Defined Properties:')
            message('-'*18)
            for attr, func_name in self._det_config['property'].items():
                #val = getattr(self, func_name)
                val = self._get_property(attr)
                strval = _repr_value(val)
                fdict = {'attr': attr, 'str': strval, 'unit': '', 'doc': ''}
                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))

        return message

    def _get_info(self, attr):
        info = self.detector._attr_info.get(attr)
        if info:
            info({'type': 'detector'})
            return info

        for typ in ['count','histogram','parameter','peak','projection','property']:
            info = self._det_config.get(typ).get(attr)
            if info:
                info.update({'type': typ})
                return info

        return {}


    def show_all(self, **kwargs):
        """
        Show detailed detector information for current event.
        """
        message = Message(quiet=True, **kwargs)
        message('-'*80)
        message(str(self))
        message('-'*80)
        message('Event Data:')
        message('-'*18)
        self.evtData.show_info(append=True)

        self._show_user_info(append=True)

        if self._tabclass == 'detector':
            message('-'*80)
            message('Processed Data:')
            message('-'*18)
            self.detector.show_info(append=True)
            if self._calib_class:
                message('-'*80)
                message('Calibration Data:')
                message('-'*18)
                self.calibData.show_info(append=True)

        if self.configData:
            message('-'*80)
            message('Configuration Data:')
            message('-'*18)
            self.configData.show_info(append=True)
        
        if self.epicsData:
            message('-'*80)
            message('Epics Data:')
            message('-'*18)
            self.epicsData.show_info(append=True)
               
        return message

    def show_info(self, **kwargs):
        """
        Show basic detector information, including from user defined AddOn methods, 
        for current event.
        """
        message = Message(quiet=True, **kwargs)
        message('-'*80)
        message(str(self))
        message('-'*80)
        getattr(self, self._tabclass).show_info(append=True)
        self._show_user_info(append=True)

        return message

    @property
    def sourceData(self):
        """
        Source information for detector.
        """
        return getattr(self._ds.configData.Sources, self._alias)

    @property
    def configData(self):
        """
        Configuration data for detector.
        """
        return getattr(self._ds.configData, self._alias)

    @property
    def evtData(self):
        """
        Tab accessible raw data from psana event keys.
        """
        if self._alias not in self._ds._current_evtData:
            self._ds._current_evtData.update({self._alias: 
                PsanaSrcData(self._ds._current_evt, self._srcstr, key_info=self._ds._evt_keys)})

        return self._ds._current_evtData.get(self._alias)

    @property
    def epicsData(self):
        """
        Epics information for current detector.
        """
        return getattr(self._ds.epicsData, self._alias)

    @property
    def detector(self):
        """
        Raw, calib and image data using psana.Detector class.
        Improved speed with data cashing when accessing the same object multiple times for
        the same event (e.g., multiple roi or other access for same data).
        
        See Also
        --------
        ImageData object
        ImageCalibData object
        WaveformData object
        WaveformCalibData object
        IpimbData object
        
        """
        if self._pydet:
            if self._alias not in self._ds._current_data:
                #opts = self._det_config.get('opts', {})
                #self._ds._current_data.update({self._alias: self._det_class(self._pydet, self._ds._current_evt, opts=opts)})
                self._ds._current_data.update({self._alias: self._det_class(self._pydet, self._ds._current_evt)})
             
            return self._ds._current_data.get(self._alias)

        else:
            return None

    @property
    def calibData(self):
        """
        Calibration data using psana.Detector class
        """
        if self._pydet:
            return self._calib_class(self._pydet, self._ds._current_evt)
        else:
            return None

    def set_cmpars(self, cmpars):
        """
        Set common mode.
        """
        if 'calib' not in self._det_config['opts']:
            self._det_config['opts']['calib'] = {}
        
        # reset current data
        self._ds._current_data = {}
        # save opts for calib object
        self._det_config['opts']['calib'].update({'cmpars': cmpars})
        self._pydet.calib(self._ds._current_evt, cmpars=cmpars)

    def _get_roi(self, attr):
        """
        Get roi from roi_name as defined by AddOn.
        """
        if attr in self._det_config['roi']:
            item = self._det_config['roi'][attr]
            #img = getattr(self, item['attr'])
            #img = self._getattr(item['attr'])
            img = getattr_complete(self, item['attr'])
            if img is not None:
                roi = item['roi']
                if len(img.shape) == 1:
                    return img[roi[0]:roi[1]]

                sensor = item.get('sensor')
                if sensor is not None:
                    img = img[sensor]
                    
                return img[roi[0][0]:roi[0][1],roi[1][0]:roi[1][1]]
            else:
                return None
        else:
            return None

    @property
    def psplots(self):
        """
        To kill a plot that has been created with self.add.psplot, del self.psplots[name]
        and close the plot window.  
           
        If you only close the plot window it will automatically reopen on the next event.
        If the plot is not updating as expected, simply close the window and it will refresh
        on the next event.

        Example
        -------
        evt.DscCsPad.add.projection('calib','r',publish=True)
        del evt.DscCsPad.psplots['DscCsPad_calib_r']
        
        evt.DscCsPad.add.psplot('image')                
        del evt.DscCsPad.psplots['DscCsPad_image']

        """
        return self._det_config['psplot']

    def _get_count(self, attr):
        """
        Get counts from count_name as defined by AddOn.
        
        Parameters
        ----------
        attr : str
            Attribute name
        """
        if attr in self._det_config['count']:
            item = self._det_config['count'][attr]
            #img = getattr(self, item['attr'])
            #img = self._getattr(item['attr'])
            img = getattr_complete(self, item['attr'])
            gain = item.get('gain', 1.)
            limits = item.get('limits')
            if limits:
                return img[(img >= limits[0]) & (img < limits[1])].sum()*gain
            else:
                return img.sum()*gain

        else:
            return None

    def _get_histogram(self, attr):
        """
        Returns histogram as defined by AddOn.
        """
        if attr in self._det_config['histogram']:
            item = self._det_config['histogram'][attr]
            img = getattr_complete(self, item['attr'])
            gain = item.get('gain', 1.)
            hst, hbins = np.histogram(img*gain, item.get('bins'), 
                    weights=item.get('weights'), density=item.get('density'))

            return hst
        else:
            return None

    def _get_peak(self, attr):
        """
        Returns peak information as defined in AddOn class.
        
        Parameters
        ----------
        attr : str
            Attribute name
        """
        if attr in self._det_config['peak']:
            item = self._det_config['peak'][attr]
            wf = getattr(self, item['attr'])
            ichannel = item.get('ichannel')
            if ichannel is not None:
                wf = wf[ichannel]

            background = item.get('background')
            if background:
                wf -= background

            scale = item.get('scale')
            if scale:
                wf *= scale

            method = item.get('method')
            if method == 'waveform':
                return wf
            
            roi = item.get('roi')
            if roi:
                wf = wf[roi[0]:roi[1]]

            wf = list(wf)
            maxval = max(wf)
            if method == 'max':
                return maxval
            
            if max > item.get('threshold'):
                idx = wf.index(maxval)
                if roi:
                    idx += roi[0] 
            else:
                idx = 0        
    
            if method == 'index':
                return idx

            if method in ['time', 'pos']:
                xaxis = item.get('xaxis')
                if xaxis is not None:
                    return xaxis[idx]

        return None
 
    def _get_projection(self, attr):
        """
        Get projection as defined by AddOn.
        
        Parameters
        ----------
        attr : str
            Attribute name
        """
        item = self._det_config['projection'].get(attr)
        if item is None:
            return None

        #img = getattr(self, item['attr'])
        img = getattr_complete(self, item['attr'])
        #img = self._getattr(item['attr'])
        if img is None:
            return None

        axis = item['axis']
        if axis in ['r', 'az']:
            # make a radial histogram
            coord_compressed = item['coord_compressed']
            mask = item['mask']
            bins = item['bins']
            norm = item['norm']
            # make masked image with mask compressed
            img_compressed = np.ma.masked_array(img, mask).compressed()
            hst, hbins  = np.histogram(coord_compressed, bins=bins, weights=img_compressed)
            return hst/norm
            
        else:
            # perform method on oposite axis where psana convention is images have coordinates (x, y)
            iaxis = {'x': 0, 'y': 1}.get(axis,0)
            method = item.get('method', 'sum')
            return getattr(img, method)(axis=iaxis)

    def _get_property(self, attr):
        """
        Get property as defined by AddOn.

        Parameters
        ----------
        attr : str
            Attribute name
        """
        func_name = self._det_config['property'].get(attr)
        if hasattr(func_name,'__call__'):
            func_name = func_name(self)
        return func_name

    def __str__(self):
        return '{:} {:}'.format(self._alias, str(self._ds.events.current))

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name__, str(self))
   
    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(getattr(self, self._tabclass), attr)

        if attr in self._det_config['parameter']:
            return self._det_config['parameter'].get(attr)

        if attr in self._det_config['property']:
            return self._get_property(attr)
            
        if attr in self._det_config['count']:
            return self._get_count(attr)

        if attr in self._det_config['histogram']:
            return self._get_histogram(attr)

        if attr in self._det_config['roi']:
            return self._get_roi(attr)
       
        if attr in self._det_config['peak']:
            return self._get_peak(attr)
       
        if attr in self._det_config['projection']:
            return self._get_projection(attr)

        if attr in self._ds.events.current._event_attrs:
            return getattr(self._ds.events.current, attr)

    def __dir__(self):
        all_attrs =  set(self._attrs+
                         self._det_config['parameter'].keys() +
                         self._det_config['property'].keys() +
                         self._det_config['roi'].keys() + 
                         self._det_config['count'].keys() + 
                         self._det_config['histogram'].keys() + 
                         self._det_config['peak'].keys() + 
                         self._det_config['projection'].keys() + 
                         self._ds.events.current._event_attrs +
                         self.__dict__.keys() + dir(Detector))
        
        return list(sorted(all_attrs))


class AddOn(object):
    """
    Collection of methods to add parameters, properties, and reduction/proccesing of data 
    with roi, projection, histogram methods.
    """

    _plugins = {}
    _init_attrs = ['_ds', '_alias']

    def __init__(self, ds, alias):
        self._ds = ds
        self._alias = alias

    @property
    def _det_config(self):
        return self._ds._device_sets.get(self._alias)

    @property
    def _evt(self):
        return self._ds.events.current

    @property
    def _det(self):
        return getattr(self._evt, self._alias)

    def module(self, module=None, **kwargs):
        """Add detector module

        Parameters
        ----------
        module : str
            Name of python module that contains a user defined PyDataSource.Detector class
            with the same name as the module.  e.g., 'acqiris' loads 'acqiris.py' file 
            which must have class Acqiris(PyDatasource.Detector)
        
        Keywords
        --------
        path : str
            Name of path for python module (default is the path of PyDataSource)
        desc : str
            Description 

        Example
        -------
        >>> evt.acqiris.add.module('acqiris')

        See Also
        --------
        DataSource.add_detector

        """
        if module:
            self._ds.add_detector(self._alias, module=module, **kwargs)

    def parameter(self, **kwargs):
        """
        Add parameters as keword arguments.  
        Will be perserved if module is added or DataSource is reloaded
        and is saved along with other AddOn information with save_config.

        Examples
        --------
        
        >>> evt.acqiris.add.parameter(foo='bar', backlevel=1.)
        
        or alternatively

        >>> params = {foo='bar', backlevel=1.}
        >>> evt.acqiris.add.parameter(**params)

        """
        for param, value in kwargs.items():
            self._det_config['parameter'][param] = value 

    def property(self, func_name, *args, **kwargs):
        """
        Add a property that operates on this detector object.
        
        The result will be added as an attribute to the detecor with the
        name of the function unless attr is provided.
       
        Examples
        --------
        Import or create a method acting on self as the Detector object and add it as a property
        
        >>> def myfunc(self):       
                return self.ebeamL3Energy
        
        >>> evt.EBeam.add.property(myfunc, 'energy')

        Or alternatively using lambda:
        
        >>> evt.EBeam.add.property(lambda self: self.ebeamL3Energy, 'energy')
        
        """
        if len(args) > 0:
            attr = args[0]
        else:
            attr = func_name.func_name
        
        self._det_config['property'][attr] = func_name 


    def projection(self, attr=None, axis='x', name=None, 
            axis_name=None, method=None, 
            mask=None, bins=None, bin_size=None, rmin=None, rmax=None, 
            unit='ADU', doc='', publish=False,
            **kwargs):
        """
        Make a projection along an axis.
        
        Options implemented for x/y projections (i.e., axis='x' or axis='y')
        But radial (axis='r') and azimuth (axis='az') projections are valid 
        in limited circumstances.
        
        Parameters
        ----------
        attr : str
            Name of data object on which to make projection
        axis : str
            Projection axis
                'x': x-axis 
                'y': y-axis
                'r': radial
                'az': azimuth
                True: both 'x' and 'y' projections
        name : str
            Name of projection object [Default is to append '_'+axis and sequential number
            to input attr name.
        axis_name : str
            name of axis [default = axis+name]
        method : str
            by default the method is 'sum' but other numpy methods are
            also possible (e.g., 'mean', 'std', 'min', 'max', 'var').
        roi : tuple, optional
            Region of interest (roi) parameters passed to roi method.
            roi method then acts on this reduced data
        mask : str, optional
            Name of mask to apply before making projection.
        bins : int or sequence of scalars, optional
            If `bins` is an int, it defines the number of equal-width
            bins in the given range (10, by default). If `bins` is a sequence,
            it defines the bin edges, including the rightmost edge, allowing
            for non-uniform bin widths. (used with np.histogram)
        bin_size : float, optional
            Size of bins for polar coordinate projections.
            Default = pixelsize
        doc : str, optional
            Doc string for resulting projection data
        unit : str, optional
            Units of roi data [Default assumes same as attr data]
        publish : bool, optional
            Make psplot of roi data
 
        """
        _methods = ['sum', 'mean', 'std', 'min', 'max', 'var']
        _cartesian_axes = ['x', 'y']
        _polar_axes = ['r', 'az']

        axis = axis.lower()
        xunit = ''

        if not attr:
            if axis in _polar_axes:
                attr = 'calib'

            else:
                if self._det.image is not None:
                    attr = 'image'
                elif self._det.calib is not None:
                    attr = 'calib'
                elif self._det.raw is not None:
                    attr = 'raw'
                elif self._det.evtData.data16 is not None:
                    attr = 'evtData.data16'
                else:
                    attr = 'evtData.data8'

        try:
            img = getattr_complete(self._det,attr)
        except:
            print 'Not valid'
            return
 
        if axis in _polar_axes:
            if not method:
                method = 'norm'
            elif method not in ['norm']:
                print 'ERROR: {:} is not a valid method'.format(method)
                print ' - only norm method is valid for radial projections'

        elif axis in _cartesian_axes:
            if not method:
                method = 'sum'

            elif method not in _methods:
                print 'ERROR: {:} is not a valid method'.format(method)
                print ' - method must be in {:}'.format(_methods)
            
            if len(img.shape) != 2:
                print '{:} is not a 2D image -- cannot make projection'.format(attr)
                return
        
        else:
            print 'ERROR:  {:} is not a valid axis'.format(axis)
            print ' - Valid Cartesian Options = {:}'.format(_cartesian_axes)
            print ' - Valid Polar Options = {:}'.format(_polar_axes)
            return 

        if not axis_name:
            axis_name = axis+attr
        
        if not name:
            name = attr+'_'+axis

        calibData = self._det.calibData
        if axis in _polar_axes and calibData.coords_x is not None:
            coords_x = calibData.coords_x
            coords_y = calibData.coords_y
            if not mask:
                mask = -calibData.mask() 

            coords_r = np.sqrt(coords_y**2+coords_x**2)
            coords_az = np.degrees(np.arctan2(coords_y, coords_x))

            if axis == 'r':
                if not xunit:
                    xunit = 'um'
                coord_hist = np.ma.masked_array(coords_r, mask)
                if not bins:
                    if not bin_size:
                        bin_size = calibData.pixel_size
                    
                    bins = np.arange(coord_hist.compressed().min()+bin_size*10, 
                                     coord_hist.compressed().max()-bin_size*10., 
                                     bin_size)
     
            else:
                if rmin and rmax and np.array(rmin).size > 1 and np.array(rmax).size > 1:
                    # in future
                    print 'Vectors for rmin and rmax not yet supported'
                    return

                else:
                    if rmin:
                        # add logical or for rmin
                        mask |= np.ma.masked_less(coords_r, rmin).mask

                    if rmax:
                        # add logical or for rmax
                        mask |= np.ma.masked_greater_equal(coords_r, rmax).mask

                    coord_hist = np.ma.masked_array(coords_az, mask)
                
                if not bins:
                    if not bin_size:
                        bin_size = 2.

                    bins = np.arange(-180., 180., bin_size)

            coord_compressed = coord_hist.compressed()
            norm, hbins = np.histogram(coord_compressed, bins=bins)
            if method != 'norm':
                norm = 1.
            
            if doc == '':
                doc = "{:}-axis projection of {:} data".format(axis, attr)
            
            projaxis = (hbins[1:]+hbins[0:-1])/2.
            self._det_config['xarray']['coords'].update({axis_name: projaxis})

            self._det_config['xarray']['dims'].update(
                    {name: ([axis_name], (projaxis.size))})

            self._det_config['projection'].update(
                    {name: {'attr': attr, 
                            'axis': axis, 
                            'method': method,
                            'axis_name': axis_name,
                            'coord_compressed': coord_compressed,
                            'mask': mask,
                            'bins': bins,
                            'rmin': rmin,
                            'rmax': rmax,
                            'norm': norm,
                            'xunit': xunit,
                            'unit': unit,
                            'doc': doc,
                            'xdata': projaxis}})

        else:
            projaxis = self._det_config['xarray']['coords'].get(axis_name) 
           
            # Need to add in auto axis for Data Arrays
            if not xunit and not projaxis:
                xunit = 'pixel'

            if projaxis is None:
                iaxis = {'x': 1, 'y': 0}.get(axis)
                projaxis = np.arange(img.shape[iaxis])    
                self._det_config['xarray']['coords'].update({axis_name: projaxis})


            self._det_config['xarray']['dims'].update(
                    {name: ([axis_name], (projaxis.size))})

            self._det_config['projection'].update(
                    {name: {'attr': attr, 
                            'axis': axis, 
                            'xunit': xunit, 
                            'method': method,
                            'axis_name': axis_name, 
                            'unit': unit,
                            'doc': doc,
                            'xdata': projaxis}})

        if publish:

            self.psplot(name)

    def roi(self, attr=None, sensor=None, roi=None, name=None, xaxis=None, yaxis=None, 
                doc='', unit='ADU', publish=False, projection=None, **kwargs):       
        """
        Make roi for given attribute, by default this is given the name img.

        Parameters
        ----------
        attr : str
            Name of data object on which to make roi
        sensor : int
            First array element for 3 dim objects
        roi : tuple
            For 1 dim objects, roi is a tuple (xstart, xend)
            For 2 dim objects, roi is a tuple ((ystart, yend), (xstart, xend))
            For 3 dim objects (e.g., cspad raw, calib), use sensor keyword to 
            sepcify the sensor and roi as ((ystart, yend), (xstart, xend)).
        name : str
            Name of roi object [Default is to append '_roi' and sequential number
            to input attr name.
        xaxis: array_like
            X-axis coordinate of roi
        yaxis: array_like
            Y-axis coordinate of roi
        doc : str
            Doc string for resulting roi data
        unit : str
            Units of roi data [Default assumes same as attr data]
        publish : bool
            Make psplot of roi data
        projection : bool
            Make projection(s) of data.  See projection method. 
        
        """
        if not attr:
            if sensor is not None:
                attr = 'calib'
            else:
                attr = 'image'

        if not roi:
            try:
                img = self._getattr(attr)
                if sensor is not None:
                    img = img[sensor]

                plotMax = np.percentile(img, 99.5)
                plotMin = np.percentile(img, 5)
                print 'using the 5/99.5% as plot min/max: (',plotMin,',',plotMax,')'
                fig=plt.figure(figsize=(20,10))
                gs=plt.matplotlib.gridspec.GridSpec(1,2,width_ratios=[2,1])
                plt.subplot(gs[0]).imshow(img,clim=[plotMin,plotMax],interpolation='None')

                print 'Select two points to form ROI to zoom in on target location.'
                p = np.array(ginput(2))
                roi = ([int(p[:,1].min()),int(p[:,1].max())],
                       [int(p[:,0].min()),int(p[:,0].max())])
                print 'Selected ROI [y, x] =', roi
            except:
                print 'Cannot get roi'
                return None

        #if len(roi) == 3:
        #    xroi = roi[2]
        #    yroi = roi[1]
        #else:
        if not name:
            nroi = len(self._det_config['roi'])
            if nroi == 0:
                name = 'roi'
            else:
                name = 'roi'+str(nroi+1)

        img = self._getattr(attr)
        if len(img.shape) == 1:
            xroi = roi
            xaxis_name = 'x'+name
            if not xaxis or len(xaxis) != xroi[1]-xroi[0]:
                xaxis = np.arange(xroi[0],xroi[1])    
            
            if doc == '':
                doc = "{:} ROI of {:} data".format(name, attr)

            xattrs = {}
            xattrs.update({'doc': doc, 'unit': unit, 'roi': roi})
            if sensor is not None:
                xattrs.update({'sensor': sensor})
            
            self._det_config['xarray']['coords'].update({xaxis_name: xaxis})
            self._det_config['xarray']['dims'].update(
                    {name: ([xaxis_name], (xaxis.size), xattrs)})

            self._det_config['roi'].update({name: {'attr': attr, 
                                                   'roi': roi,
                                                   'sensor': sensor,
                                                   'xaxis': xaxis,
                                                   'doc': doc,
                                                   'unit': unit}})
 
        else:
            xroi = roi[1]
            yroi = roi[0]

            xaxis_name = 'x'+name
            if not xaxis or len(xaxis) != xroi[1]-xroi[0]:
                xaxis = np.arange(xroi[0],xroi[1])    
            
            yaxis_name = 'y'+name
            if not yaxis or len(yaxis) != yroi[1]-yroi[0]:
                yaxis = np.arange(yroi[0],yroi[1])    
            
            if doc == '':
                doc = "{:} ROI of {:} data".format(name, attr)

            xattrs = {}
            xattrs.update({'doc': doc, 'unit': unit, 'roi': roi})
            if sensor is not None:
                xattrs.update({'sensor': sensor})
            
            self._det_config['xarray']['coords'].update({xaxis_name: xaxis, 
                                                yaxis_name: yaxis})
            self._det_config['xarray']['dims'].update(
                    {name: ([yaxis_name, xaxis_name], (yaxis.size, xaxis.size), xattrs)})

            self._det_config['roi'].update({name: {'attr': attr, 
                                                   'roi': roi,
                                                   'sensor': sensor,
                                                   'xaxis': xaxis,
                                                   'yaxis': yaxis, 
                                                   'doc': doc,
                                                   'unit': unit}})

        if projection:
            if projection in [True, 'x']:
                self.projection(name, axis='x', publish=publish, **kwargs)
            if projection in [True, 'y']:
                self.projection(name, axis='y', publish=publish, **kwargs)
        
        elif publish:
            self.psplot(name)

        return name

    def count(self, attr=None, gain=None, unit=None, doc=None, 
            roi=None, name=None, limits=None, **kwargs):
        """
        Count (i.e., sum) of detector within optional roi.

        Parameters
        ----------
        attr : str
            Name of data object in detector object on which to act
        gain: float
            optional converion from ADU to for example X-rays.
        limits: tuple
            (low, high) values to be counted.
        doc : str
            Doc string for resulting roi data
        unit : str
            Units of histogramed data.  Default ADU (times gain factor if supplied) 
        roi : tuple, optional
            Region of interest (roi) parameters passed to roi method.
            roi method then acts on this reduced data
        
        """
        if gain:
            if not unit:
                unit = 'ADUx{:.2g}'.format(gain)

        else:
            gain = 1
            if not unit:
                unit = 'ADU'

        if roi:
            if name:
                roi_name = 'roi_'+name
            else:
                roi_name = None

            roi_name = self.roi(attr, roi=roi, unit=unit, doc=doc, name=roi_name, **kwargs)
            xattrs = self._det_config['xarray']['dims'][roi_name][2]
            if not doc:
                doc = 'Sum of {:} within roi={:}'.format(attr, roi)
       
        else:
            roi_name = attr
            xattrs = {}
            if not doc:
                doc = 'Sum of {:}'.format(attr)


        if not name:
            ncount = len(self._det_config['count'])
            if ncount == 0:
                name = roi_name+'_count'
            
            else:
                name = roi_name+'_count'+str(ncount+1)


        self._det_config['count'].update({name: {'attr': roi_name, 
                                                 'gain': gain, 
                                                 'unit': unit,
                                                 'limits': limits,
                                                 'doc': doc}})

        xattrs.update({'doc': doc, 'unit': unit})
        self._det_config['xarray']['dims'].update(
                {name: ([], (), xattrs)})

    def histogram(self, attr=None, bins=None, gain=None, 
            unit=None, doc=None, roi=None, name=None, 
            weights=None, density=None, publish=None,
            **kwargs):
        """
        Make a histogram.
        
        Parameters
        ----------
        
        attr : str
            Name of data object in detector object on which to act
        bins : int or sequence of scalars, optional
            If `bins` is an int, it defines the number of equal-width
            bins in the given range (10, by default). If `bins` is a sequence,
            it defines the bin edges, including the rightmost edge, allowing
            for non-uniform bin widths. (used with np.histogram)
        gain : float, optional
            converion from ADU to for example X-rays.
        doc : str, optional
            Doc string for resulting roi data
        unit : str, optional
            Units of histogramed data.  Default ADU (times gain factor if supplied) 
        roi : tuple, optional
            Region of interest (roi) parameters passed to roi method.
            Histogram acts on this reduced data
        name : str, optional
            Name of histogram data object
        weights : array_like, optional
            An array of weights, of the same shape as `a`.  Each value in `a`
            only contributes its associated weight towards the bin count
            (instead of 1).  If `normed` is True, the weights are normalized,
            so that the integral of the density over the range remains 1
            (used with np.histogram)
        density : bool, optional
            If False, the result will contain the number of samples
            in each bin.  If True, the result is the value of the
            probability *density* function at the bin, normalized such that
            the *integral* over the range is 1. Note that the sum of the
            histogram values will not be equal to 1 unless bins of unity
            width are chosen; it is not a probability *mass* function.
            Overrides the `normed` keyword if given.
            (used with np.histogram)
        publish : bool
            Make psplot of histogram
        
        See Also
        --------
        np.histogram

        """
#        range : (float, float), optional
#            The lower and upper range of the bins.  If not provided, range
#            is simply ``(a.min(), a.max())``.  Values outside the range are
#            An array of weights, of the same shape as `a`.  Each value in `a`
#            only contributes its associated weight towards the bin count
#            (instead of 1).  If `normed` is True, the weights are normalized,
#            so that the integral of the density over the range remains 1
#            (used with np.histogram)

        if gain:
            if not unit:
                unit = 'ADUx{:}'.format(gain)

        else:
            gain = 1
            if not unit:
                unit = 'ADU'

        if roi:
            if name:
                roi_name = 'roi_'+name
            else:
                roi_name = None

            roi_name = self.roi(attr, roi=roi, unit=unit, doc=doc, name=roi_name, **kwargs)
            xattrs = self._det_config['xarray']['dims'][roi_name][2]
            if not doc:
                doc = 'Histogram of {:} within roi={:}'.format(attr, roi)
       
        else:
            roi_name = attr
            xattrs = {}
            if not doc:
                doc = 'Histogram of {:}'.format(attr)


        if not name:
            ncount = len(self._det_config['histogram'])
            if ncount == 0:
                name = roi_name+'_hist'
            
            else:
                name = roi_name+'_hist'+str(ncount+1)
            
        if not hasattr(bins, 'shape') or bins.shape[0] < 3:
            img = self._getattr(roi_name)
            hst, bins = np.histogram(img, bins, 
                    weights=weights, density=density)

        xaxis = (bins[1:]+bins[:-1])/2.

        self._det_config['histogram'].update({name: {'attr': roi_name, 
                                                     'gain': gain, 
                                                     'unit': unit,
                                                     'bins': bins,
                                                     'xaxis': xaxis, 
                                                     'weights': weights,
                                                     'density': density,
                                                     'doc': doc}})

        xattrs.update({'doc': doc, 'unit': unit})
        self._det_config['xarray']['coords'].update({name+'_xaxis': xaxis})
        self._det_config['xarray']['dims'].update(
                {name: ([name+'_xaxis'], (xaxis.shape), xattrs)})

        if publish:
            xlabel = '[{:}]'.format(unit)
            self.psplot(name, 
                        xdata=xaxis, 
                        xlabel=xlabel)


    def peak(self, attr=None, ichannel=None, name=None,
            xaxis=None, roi=None, scale=1, baseline=None,
            methods=None,
            threshold=None, 
            docs={}, units={}):
        """
        Simple 1D peak locator.
           
        Parameters
        ----------
        
        attr : str
            Name of data object on which to find peaks
        ichannel : int
            acqiris waveform channels start with 1.  
            If not present, peak locators will be created for alll chanels
        name : str
            Name of peak object [Default is to append '_peak' and sequential number
            to input attr name.
        xaxis: array_like
            X-axis coordinate of data object
            Default is to use wftime for attr='waveform'
        threshold : float
            Peak threshold.  default threshold is 1.5% of full range for Acqiris
        baseline : float
            Baseline level to subtract
        scale : float
            Peak scale factor
        method : str
            Peak finding method options include:
            'index': index at max channel.
            'max': maximum value.
        roi : tuple, optional
            Region of interest 
        docs : dict
            Doc strings for resulting peaks
        units : dict
            Units of peaks data [Default assumes same as attr data]
 
        """
        
        if not attr:
            if self._det._pydet_name == 'WFDetector':
                if self._det.__class__.__name__ == 'Detector':
                    self._det.add.module('acqiris')

                attr = 'waveform'
                if ichannel is None and not name:
                    for i in range(self._det.waveform.shape[0]):
                        print 'adding ichannel', i
                        self.peak(ichannel=i, xaxis=xaxis, roi=roi, scale=scale, 
                                  theshold=threshold, baseline=baseline, methods=None,
                                  docs=docs,units=units)
                    
                    return

        if not methods:
            methods = {'index': 'index', 'max': 'max', 'pos': 'pos'}
            if attr == 'waveform':
                methods.pop('index')
                methods.update({'time': 'time', 'waveform': 'waveform'})

        attr_info = self._det._get_info(attr)

        if not units:
            if attr == 'waveform':
                units = {'time': 's', 'index': 'channel', 'max': 'V', 'waveform': 'V'}
            else:
                units = {'max': '', 'index': ''}
                #units = {'max': attr_info.get('unit'), 'index': 'bin'}

        if not name:
            if attr == 'waveform':
                name = 'peak'
            else:
                name = attr+'_peak'
            
            if ichannel is not None:
                name += '_ch{:}'.format(ichannel+1)

        if not xaxis:
            if attr == 'waveform' and ichannel is not None:
                xaxis = self._det.wftime[ichannel]
            elif 'xaxis' in attr_info:
                xaxis = attr_info.get('xaxis')
            elif 'bins' in attr_info:
                xaxis = attr_info.get('bins')

        if not threshold:
            if self._det._pydet.dettype == 16:
                threshold = self._det.configData.vert.fullScale[ichannel]*0.015
            else:
                threshold = 0.

        for mname, method in methods.items():
            # make entry for each peak method
            pname = '_'.join([name, mname])
            doc = docs.get(mname, '')
            if not doc:
                doc = '{:} {:} {:}'.format(self._alias, name, method)
                if method not in ['waveform']:
                    doc+=' of peak'

            unit = units.get(mname, '')

            self._det_config['peak'].update({pname:   
                    {'attr': attr,
                     'ichannel': ichannel,
                     'roi': roi,
                     'baseline': baseline,
                     'threshold': threshold, 
                     'xaxis': xaxis,
                     'scale': scale,
                     'doc': doc,
                     'unit': unit,
                     'method': method,
                     }})

            if method in ['waveform']:
                axis_name = '_'.join([name,'t'])
                projaxis = self._det.wftime[ichannel]
                self._det_config['xarray']['coords'].update({axis_name: projaxis})
                self._det_config['xarray']['dims'].update(
                    {pname: ([axis_name], (projaxis.size))})
                
            else:
                self._det_config['xarray']['dims'].update(
                        {pname: ([], (), {'doc': doc, 'unit': unit})}
                        )

#    def mask(self, attr):
#        img = self._getattr(attr)
#        plotMax = np.percentile(img, 99.5)
#        plotMin = np.percentile(img, 5)
#        print 'using the 5/99.5% as plot min/max: (',plotMin,',',plotMax,')'
#
##        image = self.__dict__[detname].image(self.lda.run, img)
##        det = self.__dict__[detname]
##        x = self.__dict__[detname+'_x']
##        y = self.__dict__[detname+'_y']
##        iX = self.__dict__[detname+'_iX']
##        iY = self.__dict__[detname+'_iY']
#        x = self._getattr()
#        extent=[x.min(), x.max(), y.min(), y.max()]
#
#        fig=plt.figure(figsize=(10,6))
#        from matplotlib import gridspec
#        gs=gridspec.GridSpec(1,2,width_ratios=[2,1])
#        
#        mask=None
#        mask_r_nda=None
#        select=True
#        while select:
#            plt.subplot(gs[0]).imshow(image,clim=[plotMin,plotMax],interpolation='None')
#
#            shape = raw_input("rectangle(r), circle(c) or polygon(p)?:\n")
#            if shape=='r':
#                print 'select two corners: '
#                p =np.array(ginput(2))
#                mask_roi=np.zeros_like(image)
#                mask_roi[p[:,1].min():p[:,1].max(),p[:,0].min():p[:,0].max()]=1
#                mask_r_nda = np.array( [mask_roi[ix, iy] for ix, iy in zip(iX,iY)] )
#                plt.subplot(gs[1]).imshow(det.image(self.lda.run,mask_r_nda))
#                print 'mask from rectangle (shape):',mask_r_nda.shape
#                if raw_input("Done?\n") in ["y","Y"]:
#                    select = False
#            elif shape=='c':
#                plt.subplot(gs[0]).imshow(np.rot90(image),clim=[plotMin,plotMax],interpolation='None',extent=(x.min(),x.max(),y.min(),y.max()))
#                if raw_input("Select center by mouse?\n") in ["y","Y"]:
#                    c=ginput(1)
#                    cx=c[0][0];cy=c[0][1]
#                    print 'center: ',cx,' ',cy
#                else:
#                    ctot = raw_input("center (x y)?\n")
#                    c = ctot.split(' ');cx=float(c[0]);cy=float(c[1]);
#                if raw_input("Select outer radius by mouse?\n") in ["y","Y"]: 
#                    r=ginput(1)
#                    rox=r[0][0];roy=r[0][1]
#                    ro=np.sqrt((rox-cx)**2+(roy-cy)**2)
#                    if raw_input("Select inner radius by mouse?\n") in ["y","Y"]:
#                        r=ginput(1)
#                        rix=r[0][0];riy=r[0][1]
#                        ri=np.sqrt((rix-cx)**2+(riy-cy)**2)
#                    else:
#                        ri=0
#                    print 'radii: ',ro,' ',ri
#                else:
#                    rtot = raw_input("radii (r_outer r_inner)?\n")
#                    r = rtot.split(' ');ro=float(r[0]);ri=max(0.,float(r[1]));        
#                mask_router_nda = np.array( [(ix-cx)**2+(iy-cy)**2<ro**2 for ix, iy in zip(x,y)] )
#                mask_rinner_nda = np.array( [(ix-cx)**2+(iy-cy)**2<ri**2 for ix, iy in zip(x,y)] )
#                mask_r_nda = mask_router_nda&~mask_rinner_nda
#                print 'mask from circle (shape):',mask_r_nda.shape
#                plt.subplot(gs[1]).imshow(det.image(self.lda.run,mask_r_nda))
#                if raw_input("Done?\n") in ["y","Y"]:
#                    select = False
#            elif shape=='p':
#                plt.subplot(gs[0]).imshow(np.rot90(image),clim=[plotMin,plotMax],interpolation='None',extent=(x.min(),x.max(),y.min(),y.max()))
#                nPoints = int(raw_input("Number of Points (-1 until right click)?\n"))
#                p=np.array(ginput(nPoints))
#                print p
#                mpath=path.Path(p)
#                all_p = np.array([ (ix,iy) for ix,iy in zip(x.flatten(),y.flatten()) ] )
#                mask_r_nda = np.array([mpath.contains_points(all_p)]).reshape(x.shape)
#                plt.subplot(gs[1]).imshow(det.image(self.lda.run,mask_r_nda))
#                print 'mask from polygon (shape):',mask_r_nda.shape
#                print 'not implemented yet....'
#                if raw_input("Done?\n") in ["y","Y"]:
#                    select = False
#
#            if mask_r_nda is not None:
#                print 'created a mask....'
#                if mask is None:
#                    mask = mask_r_nda.astype(bool).copy()
#                else:
#                    mask = np.logical_or(mask,mask_r_nda)
#            print 'masked now: ',np.ones_like(x)[mask_r_nda.astype(bool)].sum()
#            print 'masked tot: ',np.ones_like(x)[mask.astype(bool)].sum()
#
#            fig=plt.figure(figsize=(6,6))
#            plt.show()
#            image_mask = img.copy(); image_mask[mask]=0;
#            plt.imshow(det.image(self.lda.run,image_mask),clim=[plotMin,plotMax])
#
#        if det.is_cspad2x2():
#            mask=mask.reshape(2,185*388).transpose(1,0)
#        else:
#            mask=mask.reshape(32*185,388)
#        #2x2 save as 71780 lines, 2 entries
#        #cspad save as 5920 lines, 388 entries
#        if raw_input("Save to calibdir?\n") in ["y","Y"]:
#            if raw_input("Invert?\n") in ["n","N"]:
#                mask = (~(mask.astype(bool))).astype(int)
#            srcStr=det.source.__str__().replace('Source("DetInfo(','').replace(')")','')
#            if det.is_cspad2x2():
#                dirname='/reg/d/psdm/%s/%s/calib/CsPad2x2::CalibV1/%s/pixel_mask/'%(self.lda.expname[:3],self.lda.expname,srcStr)
#            else:
#                dirname='/reg/d/psdm/%s/%s/calib/CsPad::CalibV1/%s/pixel_mask/'%(self.lda.expname[:3],self.lda.expname,srcStr)        
#            if not os.path.exists(dirname):
#                os.makedirs(dirname)
#            fname='%s-end.data'%self.lda.run
#            np.savetxt(dirname+fname,mask)
#        elif raw_input("Save to local?\n") in ["y","Y"]:
#            if raw_input("Invert?\n") in ["n","N"]:
#                mask = (~(mask.astype(bool))).astype(int)
#            np.savetxt('%s_mask_run%s.data'%(self.lda.expname,self.lda.run),mask)
#        return mask

    def psplot(self, *attrs, **kwargs):
        """
        Add psplot.

        Parameters
        ----------
              
        local: bool
            open psplot locally (default)
        eventCode: int
            check if event code(s) are in data 
            (or alternatively not in date with - sign)
            see is_eventCodePresent
       
        Keywords
        --------
        title : str
            Plot title
        eventCode : list
            Plot if eventCode is present

        """
        plot_error = '' 
        alias = self._alias

        if len(attrs) == 0:
            print 'A string value specifying the plot object must be suppied'
            return

        if isinstance(attrs[0], list):
            attrs = attrs[0]

        attr_name = '_and_'.join(attrs)
        attr = attrs[0]

        # by default 
        if kwargs.get('local') is False:
            local = False
        else:
            local = True
        
        if 'eventCode' in kwargs:
            ecstrs = []
            for ec in kwargs.get('eventCode'):
                if ec > 0:
                    ecstrs.append(str(ec))
                else:
                    ecstrs.append('not'+str(-ec))
            ecname = '_'+'_and_'.join(ecstrs)
            ectitle = ' '+' and '.join(ecstrs)
        else:
            ecname = ''
            ectitle = ''

        if 'name' in kwargs:
            name = kwargs['name']
        else:
            name = alias+'_'+attr_name+ecname

        if 'title' in kwargs:
            title = kwargs['title']
        else:
            title = alias+' '+attr_name+ectitle
        
        if 'ts' in kwargs:
            ts = kwargs['ts']
        else:
            ts = self._ds._ievent

        if 'plot_type' in kwargs:
            plot_type = kwargs['plot_type']
        else:
            plot_type = None

        pub_opts = ['eventCode']
        pub_kwargs = {key: item for key, item in kwargs.items() \
                      if key in pub_opts}

        if not plot_error and plot_type not in ['Image','XYPlot']:
            try:
                ndim = self._getattr(attr).ndim
                if ndim == 2:
                    plot_type = 'Image'
                elif ndim == 1:
                    plot_type = 'XYPlot'
                else:
                    plot_error = 'Data with ndim = {:} not valid'.format(ndim)
            except:
                plot_error = 'Data must be numpy array of one or two dimensions.\n'               
        
        if not plot_error:
            if plot_type is 'Image':
                plt_opts = ['xlabel', 'ylabel', 'aspect_ratio', 'aspect_lock', 'scale', 'pos']
                plt_kwargs = {key: item for key, item in kwargs.items() \
                              if key in plt_opts}
               
                if attr == 'image':
                    calibData = self._getattr('calibData')
                    scale = calibData.pixel_size/1000.
                    plt_kwargs.update({ 
                            'pos': (calibData.image_xaxis[0]/1000., 
                                    calibData.image_yaxis[0]/1000.), 
                            'scale': (scale, scale),
                            })
                    if not plt_kwargs.get('xlabel'):
                        plt_kwargs['xlabel'] = 'X [mm]'
                    if not plt_kwargs.get('ylabel'):
                        plt_kwargs['ylabel'] = 'Y [mm]'

                plt_args = {'det': alias,
                            'attr': attrs,  
                            'name': name,
                            'plot_function': plot_type,
                            'ts': ts,
                            'title': title,
                            'kwargs': plt_kwargs,
                            'pubargs': pub_kwargs}
            
            elif plot_type is 'XYPlot':
                plt_opts = ['xlabel','ylabel','formats']
                plt_kwargs = {key: item for key, item in kwargs.items() \
                              if key in plt_opts}
                if 'xdata' in kwargs:
                    xdata = kwargs['xdata']
                else:
                    if attr in self._det_config['projection']:
                        xdata = self._det_config['projection'][attr]['xdata']
                        axis_name = self._det_config['projection'][attr].get('axis_name')
                        xunit = self._det_config['projection'][attr].get('xunit', '')
                        unit = self._det_config['projection'][attr].get('unit')
                        xlabel = '{:} [{:}]'.format(axis_name, xunit)
                        if not plt_kwargs.get('xlabel'):
                            plt_kwargs.update({'xlabel': xlabel})
                        if not plt_kwargs.get('ylabel'):
                            plt_kwargs.update({'ylabel': '[{:}]'.format(unit)})

                    else:
                        xdata = np.arange(len(self._getattr(attrs[0])))
                
                xdata = np.array(xdata, dtype='f')
                plt_args = {'det': alias,
                            'attr': attrs,
                            'xdata': xdata,
                            'name': name,
                            'plot_function': plot_type,
                            'ts': ts,
                            'title': title,
                            'kwargs': plt_kwargs,
                            'pubargs': pub_kwargs}
            else: 
                plot_error = 'Unknown plot type {:} \n'.format(plot_type)

        if plot_error:
            print 'Error adding psplot:' 
            print plot_error
            return None
        else:
            print 'psmon plot added -- use the following to view: '
            print '--> psplot -s {:} -p 12301 {:}'.format(os.uname()[1], name)
            print 'WARNING -- see notice when adding for -p PORT specification'
            print '           if default PORT=12301 not available'
            if 'psplot' not in self._det_config:
                self._det_config['psplot'] = {}

            self._det_config['psplot'][name] = plt_args
            if not publish.initialized:
                publish.init(local=local)
            
            if local:
                psmon_publish(self._evt)  

#    def __getattr__(self, attr):
#        if attr in self._plugins:
#            plugin = self._plugins.get(attr)
#            return plugin(self._ds)._det_add(attr)
#            if plugin:
#                return getattr(plugin, 'add')

#    def __setattr__(self, attr, val):
#        if attr not in self._init_attrs:
#            self._plugins.update({attr: val})

    def _getattr(self, attr):
        """
        Get detector attribute.
        """
        return getattr_complete(self._det,attr)

    def __dir__(self):
        all_attrs =  set(self._plugins.keys() +
                         self.__dict__.keys() + dir(AddOn))
        
        return list(sorted(all_attrs))


class IpimbData(object):
    """Tab accessibile dictified psana.Detector object.
       
       Attributes come from psana.Detector 
       with low level implementation done in C++ or python.  
       Boost is used for the C++.
    """

    _attrs = ['channel', 'sum', 'xpos', 'ypos'] 

    _attr_info = {
            'channel':     {'doc': 'Array of 4 channel values',
                            'unit': 'V'},
            'sum':         {'doc': 'Sum of all 4 channels',
                            'unit': 'V'},
            'xpos':        {'doc': 'Calulated X beam position',
                            'unit': 'mm'},
            'ypos':        {'doc': 'Calulated Y beam position',
                            'unit': 'mm'},
            } 

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det
        self._data = {}
    
    @property
    def instrument(self):
        """
        Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def show_info(self, **kwargs):
        """
        Show information for relevant detector attributes.
        """
        message = Message(quiet=True, **kwargs)
        try:
            items = sorted(self._attr_info.items(), key=operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
        except:
            message('No Event')

        return message

    def __getattr__(self, attr):
        if attr in self._attrs:
            if attr not in self._data:
                self._data.update({attr: getattr(self._det, attr)(self._evt)})
             
            return self._data.get(attr)


    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(IpimbData))
        
        return list(sorted(all_attrs))


#class GenaricWaveformData(object):
#    """Tab accessibile dictified psana.Detector object.
#       
#       Attributes come from psana.Detector 
#       with low level implementation done in C++ or python.  
#       Boost is used for the C++.
#    """
#
#    _attrs = ['raw', 'wftime'] 
#
#    _attr_info = {
#            'raw':    {'doc': 'Waveform array',
#                            'unit': 'V'},
#            'wftime':      {'doc': 'Waveform sample time',
#                            'unit': 's'},
#            } 
#
#    def __init__(self, det, evt):
#        self._evt = evt
#        self._det = det
#
#    def show_info(self, **kwargs):
#        """Show information for relevant detector attributes.
#        """
#        message = Message(quiet=True, **kwargs)
#        try:
#            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
#            for attr, item in items:
#                fdict = {'attr': attr, 'unit': '', 'doc': ''}
#                fdict.update(**item)
#                value = getattr(self, attr)
#                if isinstance(value, str):
#                    fdict['str'] = value
#                elif isinstance(value, list):
#                    if len(value) < 5:
#                        fdict['str'] = str(value)
#                    else:
#                        fdict['str'] = 'list'
#                elif hasattr(value,'mean'):
#                    if value.size < 5:
#                        fdict['str'] = str(value)
#                    else:
#                        fdict['str'] = '<{:.5}>'.format(value.mean())
#                else:
#                    try:
#                        fdict['str'] = '{:12.5g}'.format(value)
#                    except:
#                        fdict['str'] = str(value)
#
#                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
#        except:
#            message('No Event')
#
#        return message
#
#    def __getattr__(self, attr):
#        if attr in self._attrs:
#            return getattr(self._det, attr)(self._evt)
#
#    def __dir__(self):
#        all_attrs =  set(self._attrs +
#                         self.__dict__.keys() + dir(WaveformData))
#        
#        return list(sorted(all_attrs))
#

class WaveformData(object):
    """
    Tab accessibile dictified psana.Detector object.
       
    Attributes come from psana.Detector with low level implementation 
    done in C++ or python.  
    Boost is used for the C++.
    """

    _attrs = ['raw', 'waveform', 'wftime'] 

    _attr_info = {
            'waveform':    {'doc': 'Waveform array',
                            'unit': 'V'},
            'wftime':      {'doc': 'Waveform sample time',
                            'unit': 's'},
            } 

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det
        self._data = {}

    @property
    def instrument(self):
        """
        Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def show_info(self, **kwargs):
        """
        Show information for relevant detector attributes.
        """
        message = Message(quiet=True, **kwargs)
        try:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
        except:
            message('No Event')

        return message

    def __getattr__(self, attr):
        """
        Only access psana.Detector data once.
        """
        if attr in self._attrs:
            if attr not in self._data:
                self._data.update({attr: getattr(self._det, attr)(self._evt)})
             
            return self._data.get(attr)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(WaveformData))
        
        return list(sorted(all_attrs))


class WaveformCalibData(object):
    """
    Calibration data using psana.Detector access.
    """

    _attrs = ['runnum'] 

    _attr_info = {
            'runnum':      {'doc': 'Run number',
                            'unit': ''}
            }

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det

    @property
    def instrument(self):
        """
        Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def print_attributes(self):
        """
        Print detector attributes.
        """
        self._det.print_attributes()

    def set_calibration(self):
        """
        On/off correction of time.'
        """
        if self._det.dettype == 16:
            self._det.set_correct_acqiris_time()
        elif self._det.dettype == 17:
            self._det.set_calib_imp()

    def show_info(self, **kwargs):
        """
        Show information for relevant detector attributes.
        """
        message = Message(quiet=True, **kwargs)
        try:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
        except:
            message('No Event')

        return message

    def __getattr__(self, attr):
        if attr in self._attrs:
            return getattr(self._det, attr)(self._evt)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(WaveformCalibData))
        
        return list(sorted(all_attrs))


class ImageData(object):
    """
    Tab accessibile dictified psana Detector object.
       
    Attributes come from psana.Detector with low level implementation 
    done in C++ or python.  Boost is used for the C++.
    """
    _attrs = ['image', 'raw', 'calib', 'shape', 'size'] 
    _attr_info = {
            'shape':       {'doc': 'Shape of raw data array', 
                            'unit': ''},
            'size':        {'doc': 'Total size of raw data', 
                            'unit': ''},
            'raw':         {'doc': 'Raw data', 
                            'unit': 'ADU'},
            'calib':       {'doc': 'Calibrated data',
                            'unit': 'ADU'},
            'image':       {'doc': 'Reconstruced 2D image from calibStore geometry',
                            'unit': 'ADU'},
            } 

    #def __init__(self, det, evt, opts={}):
    def __init__(self, det, evt):
        self._evt = evt
        self._det = det
        self._data = {}
        #self._opts = opts

    @property
    def instrument(self):
        """
        Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def make_image(self, nda):
        """
        Make an image from the input numpy array based on the 
        geometry in the calib directory for this event.
        
        Parameters
        ----------
        nda : np.array
            input array
        """
        return self._det.image(self._evt, nda)

    def common_mode_correction(self, nda):
        """
        Return the common mode correction for the input numpy 
        array (pedestal-subtracted). 
        """
        return self._det.common_mode_correction(self._evt, nda)
        
    def common_mode_apply(self, nda):
        """
        Apply in place the common mode correction for the input 
        numpy array (pedestal-subtracted). 
        """
        self._det.common_mode_apply(self._evt, nda)

    def show_info(self, **kwargs):
        """
        Show information for relevant detector attributes.
        """
        message = Message(quiet=True, **kwargs)
        if self.size > 0 or self.raw is not None:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                value = getattr(self, attr)
                strval = _repr_value(value)
                fdict = {'attr': attr, 'str': strval, 'unit': '', 'doc': ''}
                fdict.update(**item)
                
#                if isinstance(value, str):
#                    fdict['str'] = value
#                elif isinstance(value, list):
#                    if len(value) < 5:
#                        fdict['str'] = str(value)
#                    else:
#                        fdict['str'] = 'list'
#                elif hasattr(value,'mean'):
#                    if value.size < 5:
#                        fdict['str'] = str(value)
#                    else:
#                        fdict['str'] = '<{:.5}>'.format(value.mean())
#                else:
#                    try:
#                        fdict['str'] = '{:12.5g}'.format(value)
#                    except:
#                        fdict['str'] = str(value)
#
                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
        else:
            message('No Event')

        return message

    def __getattr__(self, attr):
        """
        Only access psana.Detector data once.
        """
        if attr in self._attrs:
            if attr not in self._data:
#                opts = self._opts.get(attr, {})
#                self._data.update({attr: getattr(self._det, attr)(self._evt, **opts)})
                self._data.update({attr: getattr(self._det, attr)(self._evt)})
             
            return self._data.get(attr)

    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(ImageData))
        
        return list(sorted(all_attrs))


class ImageCalibData(object):
    """
    Calibration Data from psana Detector object.
    """

    _attrs = ['shape', 'size', 'ndim', 'pedestals', 'rms', 'gain', 'bkgd', 'status',
              'common_mode', 'runnum',
              'areas', 'indexes_x', 'indexes_y', 'pixel_size',
              'coords_x', 'coords_y', 'coords_z', 
              'image_xaxis', 'image_yaxis',
              ] 
    _attr_info = {
            'runnum':      {'doc': 'Run number',
                            'unit': ''},
            'shape':       {'doc': 'Shape of raw data array', 
                            'unit': ''},
            'size':        {'doc': 'Total size of raw data', 
                            'unit': ''},
            'ndim':        {'doc': 'Number of dimensions of raw data', 
                            'unit': ''},
            'pedestals':   {'doc': 'Pedestals from calibStore', 
                            'unit': 'ADU'},
            'rms':         {'doc': '', 
                            'unit': 'ADU'},
            'gain':        {'doc': 'Pixel Gain factor from calibStore', 
                            'unit': ''},
            'bkgd':        {'doc': '', 
                            'unit': ''},
            'status':      {'doc': '',
                            'unit': ''},
            'common_mode': {'doc': 'Common mode parameters', 
                            'unit': ''},
            'areas':       {'doc': 'Pixel area correction factor', 
                            'unit': ''},
            'indexes_x':   {'doc': 'Pixel X index', 
                            'unit': ''},
            'indexes_y':   {'doc': 'Pixel Y index', 
                            'unit': ''},
            'pixel_size':  {'doc': 'Pixel Size',
                            'unit': 'um'},
            'coords_x':    {'doc': 'Pixel X coordinate', 
                            'unit': 'um'},
            'coords_y':    {'doc': 'Pixel Y coordinate', 
                            'unit': 'um'},
            'coords_z':    {'doc': 'Pixel Z coordinate', 
                            'unit': 'um'},
            'image_xaxis': {'doc': 'Image X coordinate', 
                            'unit': 'um'},
            'image_yaxis': {'doc': 'Image Y coordinate', 
                            'unit': 'um'},
            } 

    def __init__(self, det, evt):
        self._evt = evt
        self._det = det
        self._info = {}

    @property
    def instrument(self):
        """
        Instrument to which this detector belongs.
        """
        return self._det.instrument()

    def _get_origin(self, **kwargs):
        """
        Get image origin indecies
        """
        ixo, iyo = self._det.point_indexes(self._evt, **kwargs)

        return ixo, iyo

    def _get_point_indexes(self, **kwargs):
        """
        """
        ixo, iyo = self._det.point_indexes(self._evt, **kwargs)
        if self.indexes_y is not None:
            ny = self.indexes_y.max()+1
            yaxis = (np.arange(ny)-iyo)*self.pixel_size
        else:
            if len(self.shape) == 2:
                yaxis = np.arange(self.shape[1])
            else:
                yaxis = None

        if self.indexes_x is not None:
            nx = self.indexes_x.max()+1
            xaxis = (np.arange(nx)-ixo)*self.pixel_size
        else:
            if len(self.shape) == 2:
                xaxis = np.arange(self.shape[0])
            else:
                xaxis = None
        
        self._info.update({'ixo': {'attr': 'ixo',
                                   'doc':  'Image x index of origin',
                                   'unit': '',
                                   'value': ixo}})
        if xaxis is not None:
            self._info.update({'xaxis': {'attr': 'xaxis',
                                         'doc':  'Reconstructed image xaxis',
                                         'unit': '',
                                         'value': xaxis}})

        self._info.update({'iyo': {'attr': 'iyo',
                                   'doc':  'Image y index of origin',
                                   'unit': '',
                                   'value': iyo}})
        if yaxis is not None:
            self._info.update({'yaxis': {'attr': 'yaxis',
                                         'doc':  'Reconstructed image yaxis',
                                         'unit': '',
                                         'value': yaxis}})

        return xaxis, yaxis

    @property
    def xaxis(self):
        """
        Reconstructed image x axis.
        """
        return self.image_xaxis
#        item = self._info.get('xaxis')
#        if item:
#            xaxis = item.get('value')
#        else:
#            xaxis, yaxis = self._get_point_indexes()
#            
#        return xaxis

    @property
    def yaxis(self):
        """
        Reconstruced image y axis.
        """
        return self.image_yaxis
#        item = self._info.get('yaxis')
#        if item:
#            yaxis = item.get('value')
#        else:
#            xaxis, yaxis = self._get_point_indexes()
#            
#        return yaxis

    def set_gain_mask_factor(factor=6.85):
        """
        Set Gain mask factor.  Default=6.85
        Passed to gain_mask(...) in the calib and image methods
        """
        self._det.set_gain_mask_factor(factor=factor)

    def set_do_offset(do_offset=True):
        """
        Switch mode of the Camera type of detector.
        Control parameter to turn on/off Camera intensity offset
        """
        self._det.set_do_offset(do_offset=do_offset)

    def mask(self, calib=True, status=True, 
                   edges=True, central=True, 
                   unbond=True, unbondnbrs=True):
        """
        Generate image mask.

        Parameters
        ----------
        calib: bool
            mask from file in calib directory.
        status: bool
            pixel status from file in calib director.
        edges: bool
            mask detector module edge pixels (mbit +1 in mask_geo).
        central: bool
            mask wide central columns (mbit +2 in mask_geo).
        unbond: bool
            mask unbonded pixels (mbit +4 in mask_geo).
        unbondnbrs: bool
            mask unbonded neighbour pixels (mbit +8 in mask_geo).
        
        Returns
        -------
        combined mask: array-like
        """
        return self._det.mask(self._evt, calib=calib, status=status, edges=edges, 
                              central=central, unbond=unbond, unbondnbrs=unbondnbrs)

    def mask_geo(self, mbits=15): 
        """
        Return geometry mask for given mbits keyword.
        Default is mbits=15 to mask edges, wide central columns,
        non-bo pixels and their neighbors

        Parameters
        ----------
        mbits: int 
            +1-edges; 
            +2-wide central cols; 
            +4 unbonded pixel; 
            +8-unbonded neighbour pixels;
        
        """
        return self._det.mask_geo(self._evt, mbits=mbits)

    def print_attributes(self):
        """
        Print detector attributes.
        """
        self._det.print_attributes()

    def show_info(self, **kwargs):
        """
        Show information for relevant detector attributes.
        """
        message = Message(quiet=True, **kwargs)
        if self.size > 0:
            items = sorted(self._attr_info.items(), key = operator.itemgetter(0))
            for attr, item in items:
                fdict = {'attr': attr, 'unit': '', 'doc': ''}
                fdict.update(**item)
                value = getattr(self, attr)
                if isinstance(value, str):
                    fdict['str'] = value
                elif isinstance(value, list):
                    if len(value) < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = 'list'
                elif hasattr(value,'mean'):
                    if value.size < 5:
                        fdict['str'] = str(value)
                    else:
                        fdict['str'] = '<{:.5}>'.format(value.mean())
                else:
                    try:
                        fdict['str'] = '{:12.5g}'.format(value)
                    except:
                        fdict['str'] = str(value)

                message('{attr:18s} {str:>12} {unit:7} {doc:}'.format(**fdict))
        else:
            message('No Event')

        return message

    def __getattr__(self, attr):
        if attr in self._attrs:
            return (getattr(self._det, attr)(self._evt))
        
    def __dir__(self):
        all_attrs =  set(self._attrs +
                         self.__dict__.keys() + dir(ImageCalibData))
        
        return list(sorted(all_attrs))


class EpicsConfig(object):
    """
    Tab Accessible configStore Epics information.
    Currently relatively simple, but expect this to be expanded
    at some point with more PV config info with daq update.
    """

    _pv_attrs = ['description', 'interval', 'pvId']

    def __init__(self, configStore):

        # move to PsanaSrcData objects
        self._pvs = {}
        for key in configStore.keys():
            if key.type() and key.type().__module__ == 'psana.Epics':
                a = configStore.get(key.type(),key.src())
                for pv in a.getPvConfig():
                    pvdict = {attr: getattr(pv, attr)() for attr in self._pv_attrs} 
                    self._pvs[pv.description()] = pvdict

    def show_info(self, **kwargs):
        message = Message(quiet=True, **kwargs)
        for alias, items in self._pvs.items():
            message('{:18s} {:}'.format(alias, item.pvId))

        return message

    def __getattr__(self, attr):
        if attr in self._pvs:
            return self._pvs.get(attr)

    def __dir__(self):
        all_attrs =  set(self._pvs.keys() +
                         self.__dict__.keys() + dir(EpicsConfig))
        
        return list(sorted(all_attrs))


class EpicsData(object):
    """
    Epics data from psana epicsStore.
    
    Parameters
    ----------
    ds : object
        PyDataSource.DataSource object
    
    Returns
    -------
    Dictified representation of ds.env().epicsStore()

    Example
    -------
    epicsStore = EpicsData(ds)
    """

    def __init__(self, ds):

        self._ds = ds

        pv_dict = {}
        epicsStore = self._ds.env().epicsStore()
        self.epicsConfig = EpicsConfig(self._ds.env().configStore())

        for pv in  epicsStore.names():
            name = re.sub(':|\.','_',pv)
            #check if valid -- some old data had aliases generated from comments in epicsArch files.
            if re.match("[_A-Za-z][_a-zA-Z0-9]*$", name) and not ' ' in name and not '-' in name:
                pvname = epicsStore.pvName(pv)
                if pvname:
                    pvalias = pv
                else:
                    pvalias = epicsStore.alias(pv)
                    pvname = pv

                pvalias = re.sub(':|\.|-| ','_',pvalias)
                components = re.split(':|\.|-| ',pv)
                if len(components) == 1:
                    components = re.split('_',pv,1)
                
                # check if alias has 2 components -- if not fix
                if len(components) == 1:
                    pv = '_'.join([components[0], components[0]])
                    components = re.split('_',pv,1)

                for i,item in enumerate(components):
                    if item[0].isdigit():
                         components[i] = 'n'+components[i]

                pv_dict[name] =  { 'pv': pvname,
                                   'alias': pvalias,
                                   'components': components,
                                 }
        self._pv_dict = pv_dict
        self._attrs = list(set([val['components'][0] for val in self._pv_dict.values()]))

    def __getattr__(self, attr):
        if attr in self._attrs:
            attr_dict = {key: pdict for key,pdict in self._pv_dict.items()
                         if pdict['components'][0] == attr}
            return PvData(attr_dict, self._ds, level=1)
        
        if attr in dir(self._ds.env().epicsStore()):
            return getattr(self._ds.env().epicsStore(),attr)

    def __dir__(self):
        all_attrs = set(self._attrs +
                        dir(self._ds.env().epicsStore()) +
                        self.__dict__.keys() + dir(EpicsData))
        return list(sorted(all_attrs))


class PvData(object):
    """
    Epics PV Data.
    """

    def __init__(self, attr_dict, ds, level=0):
        self._attr_dict = attr_dict
        self._ds = ds
        self._level = int(level)
        self._attrs = list(set([pdict['components'][level]
                                for key,pdict in attr_dict.items()]))

    def _get_pv(self, pv):
        return EpicsStorePV(self._ds.env().epicsStore(), pv)

    def show_info(self, **kwargs):
        """
        Show information from PVdictionary for all PV's starting with 
        the specified dictified base.
        (i.e. ':' replaced by '.' to make them tab accessible in python)
        """
        message = Message(self.get_info(), quiet=True, **kwargs)
        return message

    def get_info(self):
        """
        Return string representation of all PV's starting with 
        the specified dictified base.
        (i.e. ':' replaced by '.' to make them tab accessible in python)
        """
        info = ''
        items = sorted(self._attr_dict.items(), key=operator.itemgetter(0))
        for key,pdict in items:
            alias = pdict['alias']
            if alias:
                name = alias
                pv = pdict['pv']
            else:
                name = pdict['pv']
                pv = ''

            pvfunc = self._get_pv(pdict['pv'])
            value = pvfunc.value
            if pvfunc.isCtrl:
                comment = 'isCtrl'
            else:
                comment = ''

            try:
                info += '{:30s} {:12.4g} -- {:30s} {:10}\n'.format( \
                        name, value, pv, comment)
            except:
                info += '{:30s} {:>12} -- {:30s} {:10}\n'.format( \
                        name, value, pv, comment)
        return info

    def __getattr__(self, attr):
        if attr in self._attrs:
            attr_dict = {key: pdict for key,pdict in self._attr_dict.items()
                         if pdict['components'][self._level] == attr}
            if len(attr_dict) == 1:
                key = attr_dict.keys()[0]
                if len(self._attr_dict[key]['components']) == (self._level+1):
                    pv = self._attr_dict[key]['pv']
                    return self._get_pv(pv)
            if len(attr_dict) > 0:
                return PvData(attr_dict, self._ds, level=self._level+1)

    def __repr__(self):
        return self.get_info()

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(PvData))
        return list(sorted(all_attrs))


class EpicsStorePV(object):
    """
    Epics PV access from epicsStore. 
    """

    def __init__(self, epicsStore, pv):
        self._epicsStore = epicsStore
        self._pvname = pv
        self._store = epicsStore.getPV(pv)
        self._attrs = [attr for attr in dir(self._store) \
                if not attr.startswith('_')]
        self._show_attrs = [attr for attr in self._attrs \
                if attr not in ['dbr','stamp']]

    def get_info(self):
        info = '-'*80+'\n'
        info += '{:} = {:} -- {:}\n'.format(self._pvname, \
                                self.value, self.stamp)
        info += '-'*80+'\n'
        for attr in self._show_attrs:
            val = self.get(attr)
            info += '{:20} {:12}\n'.format(attr, val)
        
        return info

    def show_info(self, **kwargs):
        message = Message(self.get_info(), quiet=True, **kwargs)
        return message

    def get(self, attr):
        if attr in self._attrs:
            if attr is 'value':
                return self._epicsStore.value(self._pvname)
            else:
                val = getattr(self._store,attr)
                try:
                    if attr is 'stamp':
                        return TimeStamp(val())
                    else:
                        return val() 
                except:
                    return val
        else:
            return None

    def __str__(self):
        if len(self.data) > 1 and isinstance(self.data, np.ndarray):
            value = '<{:}>'.format(mean(self.data))
        else:
            value = self.value

        return '{:}'.format(value)

    def __repr__(self):
        return '< {:} = {:}, {:} -- {:} >'.format(self._pvname, \
                str(self), self.stamp.time, \
                self.__class__.__name__)

    def __getattr__(self, attr):
        if attr in self._attrs:
            return self.get(attr)

    def __dir__(self):
        all_attrs = set(self._attrs +
                        self.__dict__.keys() + dir(EpicsStorePV))
        return list(sorted(all_attrs))


class TimeStamp(object):
    """
    Class to represent time stamp objects
    """

    def __init__(self, stamp):
        self.sec = stamp.sec()
        self.nsec = stamp.nsec()

    @property
    def date(self):
        """
        Time stamp date representation.
        """
        return time.strftime('%Y-%m-%d', 
                time.localtime(self.sec))

    @property
    def time(self): 
        """
        Time stamp time representation.
        """
        EventTimeStr = time.strftime('%H:%M:%S',
                time.localtime(self.sec))
        EventTimeStr += '.{:04}'.format(int(self.nsec/1e5))
        return EventTimeStr

    def __str__(self):
        return '{:}.{:} sec'.format(self.sec, self.nsec)

    def __repr__(self):
        return '< {:}: {:} >'.format(self.__class__.__name_, _self.__str__)



