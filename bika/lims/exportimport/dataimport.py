from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import bikaMessageFactory as _
from bika.lims.browser import BrowserView
from bika.lims.content.instrument import getDataInterfaces
from bika.lims.exportimport import instruments
from bika.lims.exportimport.load_setup_data import LoadSetupData
from bika.lims.interfaces import ISetupDataSetList
from plone.app.layout.globals.interfaces import IViewView
from zope.interface import implements
from pkg_resources import *
from zope.component import getAdapters

import plone


class SetupDataSetList:

    implements(ISetupDataSetList)

    def __init__(self, context):
        self.context = context

    def __call__(self, projectname="bika.lims"):
        datasets = []
        for f in resource_listdir(projectname, 'setupdata'):
            fn = f+".xlsx"
            try:
                if fn in resource_listdir(projectname, 'setupdata/%s' % f):
                    datasets.append({"projectname": projectname, "dataset": f})
            except OSError:
                pass
        return datasets


class ImportView(BrowserView):

    """
    """
    implements(IViewView)
    template = ViewPageTemplateFile("import.pt")

    def __init__(self, context, request):
        super(ImportView, self).__init__(context, request)

        self.icon = ""
        self.title = _("Import")
        self.description = _("Select a data interface")

        request.set('disable_border', 1)

    def getDataInterfaces(self):
        return getDataInterfaces(self.context)

    def getSetupDatas(self):
        datasets = []
        adapters = getAdapters((self.context, ), ISetupDataSetList)
        for name, adapter in adapters:
            datasets.extend(adapter())
        return datasets

    def getProjectName(self):
        adapters = getAdapters((self.context, ), ISetupDataSetList)
        productnames = [name for name, adapter in adapters]
        if len(productnames) == 1:
            productnames[0] = 'bika.lims'
        return productnames[len(productnames) - 1]

    def __call__(self):
        if 'submitted' in self.request:
            if 'setupfile' in self.request.form or \
               'setupexisting' in self.request.form:
                lsd = LoadSetupData(self.context, self.request)
                return lsd()
            else:
                exim = instruments.getExim(self.request['exim'])
                return exim.Import(self.context, self.request)
        else:
            return self.template()


class ajaxGetImportTemplate(BrowserView):

    def __call__(self):
        plone.protect.CheckAuthenticator(self.request)
        exim = self.request.get('exim').replace(".", "/")
        return ViewPageTemplateFile("instruments/%s_import.pt" % exim)(self)
