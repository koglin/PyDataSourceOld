import os

from PyDataSource import Plugin, getattr_complete

from psmon import publish
publish.client_opts.daemon = True
from psmon.plots import Image, XYPlot, MultiPlot

class Psplot(Plugin):

    _psplots = {}

    def __init__(self, ds, **kwargs):
        Plugin.__init__(self, ds, **kwargs)
#        pass

    def add(self, alias, *attrs, **kwargs):
        """Update psplot.
           kwargs:
              local: if True open psplot locally
              eventCode: check if event code(s) are in data 
                         (or alternatively not in date with - sign)
                         see is_eventCodePresent
        """
        plot_error = '' 

        if isinstance(attrs[0],list):
            attrs = attrs[0]

        attr_name = '_and_'.join(attrs)
        attr = attrs[0]

        if kwargs.get('local'):
            local = True
        else:
            local = False
        
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
        
        if 'plot_type' in kwargs:
            plot_type = kwargs['plot_type']
        else:
            plot_type = None

        pub_opts = ['eventCode']
        pub_kwargs = {key: item for key, item in kwargs.items() \
                      if key in pub_opts}

        detector = getattr(self.evt, alias)
        print detector

        if not plot_error and plot_type not in ['Image','XYPlot']:
            try:
                ndim = getattr_complete(detector,attr).ndim
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
                plt_opts = ['xlabel', 'ylabel', 'aspect_ratio', 'aspect_lock']
                plt_kwargs = {key: item for key, item in kwargs.items() \
                              if key in plt_opts}
                plt_args = {'det': alias,
                            'attr': attrs,  
                            'name': name,
                            'plot_function': Image,
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
                    xdata = [np.arange(len(getattr_complete(detector, attr))) for attr in attrs]
                plt_args = {'det': alias,
                            'attr': attrs,
                            'xdata': xdata,
                            'name': name,
                            'plot_function': XYPlot,
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

            self._psplots[name] = plt_args
            publish.init(local=local)

    def event(self):
        eventCodes = self.evt.Evr.eventCodes
        for name, psmon_args in self._psplots.items():
            alias = psmon_args.get('det')
            eventCode = psmon_args['pubargs'].get('eventCode', None)
            if alias in self.evt._dets and eventCode is None or eventCode in eventCodes:
                detector = getattr(self.evt, alias)
                psplot_func = psmon_args['plot_function']
                if psplot_func is Image:
                    image = getattr_complete(detector, psmon_args['attr'][0])

                    psmon_fnc = psplot_func(
                                    str(self.evt),
                                    psmon_args['title'],
                                    image, 
                                    **psmon_args['kwargs'])
                elif psplot_func is XYPlot:
                    ydata = [getattr_complete(detector, attr) for attr in psmon_args['attr']]
                    psmon_fnc = psplot_func(
                                    str(self.evt),
                                    psmon_args['title'],
                                    psmon_args['xdata'],
                                    ydata,
                                    **psmon_args['kwargs'])

                print 'publish', name, event_info, psmon_args
                publish.send(name,psmon_fnc)



