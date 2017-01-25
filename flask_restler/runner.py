"""Run any resource in interactive mode."""


class Runner(object):

    def __init__(self, Resource):
        self.resource = Resource()
