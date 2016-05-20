
class addobj(object):

    def __init__(self, ds):
        self.ds = ds

    @property
    def evt(self):
        return self._ds.events.current 

