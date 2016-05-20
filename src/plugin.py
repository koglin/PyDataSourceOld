class Plugin(object):
    """DataSource plugin 
    """

    def __init__(self, ds, alias, **kwargs):
        self._ds = ds
        self._kwargs = kwargs
        self._alias = alias

#    @property
#    def evt(self):
#        """EvtDetectors object providing access to current event data in data_source
#        """
#        return self._ds.events.current 
#
#    def _det_add(self, alias):
#        return self.add(alias, *args, **kwargs)

    def add(self, *args, **kwargs):
        """Add method that is available in add method of EvtData object.
           Also available in relevent detector given by alias with alias
           automatically passed to method.
        """
        pass

    def event(self):
        """Method acted on every next event.
        """
        pass

    def step(self):
        """Method acted on every next step.
        """
        pass

    def run(self):
        """Method acted on every next run or upon loading new data_source.
        """
        pass

    def __getattr__(self, attr):
        if attr in self.evt._dets:
            return self._det_add(attr)

    def __dir__(self):
        all_attrs =  set(self.evt._dets.keys() +
                         self.__dict__.keys() + dir(Plugin))
        
        return list(sorted(all_attrs))



