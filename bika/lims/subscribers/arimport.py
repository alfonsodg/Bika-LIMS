from AccessControl import getSecurityManager
from Acquisition import aq_inner
from bika.lims import logger
from bika.lims.subscribers import doActionFor
from bika.lims.subscribers import skip
from bika.lims.utils import changeWorkflowState
from DateTime import DateTime
from Products.Archetypes.config import REFERENCE_CATALOG
from Products.Archetypes.event import ObjectInitializedEvent
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.WorkflowCore import WorkflowException
import transaction
import zope.event

def AfterTransitionEventHandler(instance, event):

    if instance.portal_type != "ARImport":
        print 'How does this happen'
        return

    # creation doesn't have a 'transition'
    if not event.transition:
        return

    instance.workflow_script_submit()
    

