""" Agilent's 'Masshunter Quant'
"""
from DateTime import DateTime
from Products.Archetypes.event import ObjectInitializedEvent
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import bikaMessageFactory as _
from bika.lims import logger
from bika.lims.browser import BrowserView
from bika.lims.idserver import renameAfterCreation
from bika.lims.utils import changeWorkflowState
from bika.lims.utils import tmpID
from cStringIO import StringIO
from datetime import datetime
from operator import itemgetter
from plone.i18n.normalizer.interfaces import IIDNormalizer
from zope.component import getUtility
import csv
import json
import plone
import zope
import zope.event
from bika.lims.exportimport.instruments.resultsimport import InstrumentCSVResultsFileParser,\
    AnalysisResultsImporter

title = "Agilent - Masshunter Quant"


def Import(context, request):
    """ Read Agilent's Masshunter Quant analysis results
    """
    infile = request.form['amhq_file']
    fileformat = request.form['amhq_format']
    artoapply = request.form['amhq_artoapply']
    override = request.form['amhq_override']
    sample = request.form.get('amhq_sample', 'requestid')
    errors = []
    logs = []

    # Load the most suitable parser according to file extension/options/etc...
    parser = None
    if not hasattr(infile, 'name'):
        errors.append(_("No file selected"))
    elif fileformat == 'csv':
        parser = MasshunterQuantCSVParser(infile)
    else:
        errors.append(_("Unrecognized file format '%s'") % fileformat)

    if parser:
        # Load the importer
        status = ['sample_received', 'attachment_due', 'to_be_verified']
        if artoapply == 'received':
            status = ['sample_received']
        elif artoapply == 'received_tobeverified':
            status = ['sample_received', 'attachment_due', 'to_be_verified']

        over = [False, False]
        if override == 'nooverride':
            over = [False, False]
        elif override == 'override':
            over = [True, False]
        elif override == 'overrideempty':
            over = [True, True]

        sam = ['getRequestID', 'getSampleID', 'getClientSampleID']
        if sample =='requestid':
            sam = ['getRequestID']
        if sample == 'sampleid':
            sam = ['getSampleID']
        elif sample == 'clientsid':
            sam = ['getClientSampleID']
        elif sample == 'sample_clientsid':
            sam = ['getSampleID', 'getClientSampleID']

        importer = MasshunterQuantImporter(parser=parser,
                                           context=context, 
                                           idsearchcriteria=sam,
                                           allowed_ar_states=status,
                                           allowed_analysis_states=None,
                                           override=over)
        importer.process()
        errors = importer.errors
        logs = importer.logs

    results = {'errors': errors, 'log': logs}

    return json.dumps(results)


class MasshunterQuantCSVParser(InstrumentCSVResultsFileParser):

    HEADERKEY_BATCHINFO = 'Batch Info'
    HEADERKEY_BATCHDATAPATH = 'Batch Data Path'
    HEADERKEY_ANALYSISTIME = 'Analysis Time'
    HEADERKEY_ANALYSTNAME = 'Analyst Name'
    HEADERKEY_REPORTTIME = 'Report Time'
    HEADERKEY_REPORTERNAME = 'Reporter Name'
    HEADERKEY_LASTCALIBRATION = 'Last Calib Update'
    HEADERKEY_BATCHSTATE = 'Batch State'
    SEQUENCETABLE_KEY = 'Sequence Table'
    SEQUENCETABLE_HEADER_DATAFILE = 'Data File'
    SEQUENCETABLE_HEADER_SAMPLENAME = 'Sample Name'
    SEQUENCETABLE_PRERUN = 'prerunrespchk.d'
    SEQUENCETABLE_MIDRUN = 'mid_respchk.d'
    SEQUENCETABLE_POSTRUN = 'post_respchk.d'
    SEQUENCETABLE_NUMERICHEADERS = ('Inj Vol',)
    QUANTITATIONRESULTS_KEY = 'Quantification Results'
    QUANTITATIONRESULTS_TARGETCOMPOUND = 'Target Compound'
    QUANTITATIONRESULTS_HEADER_DATAFILE = 'Data File'
    QUANTITATIONRESULTS_PRERUN = 'prerunrespchk.d'
    QUANTITATIONRESULTS_MIDRUN = 'mid_respchk.d'
    QUANTITATIONRESULTS_POSTRUN = 'post_respchk.d'
    QUANTITATIONRESULTS_NUMERICHEADERS = ('Resp', 'ISTD Resp', 'Resp Ratio',
                                          'Final Conc', 'Exp Conc', 'Accuracy')
    QUANTITATIONRESULTS_COMPOUNDCOLUMN = 'Compound'
    COMMAS = ','

    def __init__(self, csv):
        InstrumentCSVResultsFileParser.__init__(self, csv)
        self._end_header = False
        self._end_sequencetable = False
        self._sequences = []
        self._sequencesheader = []
        self._quantitationresultsheader = []
        self._numline = 0

    def getAttachmentFileType(self):
        return "Agilent's Masshunter Quant CSV"

    def _parseline(self, line):
        if self._end_header == False:
            return self.parse_headerline(line)
        elif self._end_sequencetable == False:
            return self.parse_sequencetableline(line)
        else:
            return self.parse_quantitationesultsline(line)

    def parse_headerline(self, line):
        """ Parses header lines

            Header example:
            Batch Info,2013-03-20T07:11:09.9053262-07:00,2013-03-20T07:12:55.5280967-07:00,2013-03-20T07:11:07.1047817-07:00,,,,,,,,,,,,,,
            Batch Data Path,D:\MassHunter\Data\130129\QuantResults\130129LS.batch.bin,,,,,,,,,,,,,,,,
            Analysis Time,3/20/2013 7:11 AM,Analyst Name,Administrator,,,,,,,,,,,,,,
            Report Time,3/20/2013 7:12 AM,Reporter Name,Administrator,,,,,,,,,,,,,,
            Last Calib Update,3/20/2013 7:11 AM,Batch State,Processed,,,,,,,,,,,,,,
            ,,,,,,,,,,,,,,,,,
        """
        if self._end_header == True:
            # Header already processed
            return 0

        if line.startswith(self.SEQUENCETABLE_KEY):
            self._end_header = True
            if len(self._header) == 0:
                self.err(_("No header found"), self._numline)
                return -1
            return 0

        splitted = [token.strip() for token in line.split(',')]

        # Batch Info,2013-03-20T07:11:09.9053262-07:00,2013-03-20T07:12:55.5280967-07:00,2013-03-20T07:11:07.1047817-07:00,,,,,,,,,,,,,,
        if splitted[0] == self.HEADERKEY_BATCHINFO:
            if self.HEADERKEY_BATCHINFO in self._header:
                self.warn(_("Header Batch Info already found. Discarding"),
                         self._numline, line)
                return 0

            self._header[self.HEADERKEY_BATCHINFO] = []
            for i in range(len(splitted) - 1):
                if splitted[i + 1]:
                    self._header[self.HEADERKEY_BATCHINFO].append(splitted[i + 1])

        # Batch Data Path,D:\MassHunter\Data\130129\QuantResults\130129LS.batch.bin,,,,,,,,,,,,,,,,
        elif splitted[0] == self.HEADERKEY_BATCHDATAPATH:
            if self.HEADERKEY_BATCHDATAPATH in self._header:
                self.warn(_("Header Batch Data Path already found. Discarding"),
                         self._numline, line)
                return 0;

            if splitted[1]:
                self._header[self.HEADERKEY_BATCHDATAPATH] = splitted[1]
            else:
                self.warn(_("Batch Data Path not found or empty"), self._numline, line)

        # Analysis Time,3/20/2013 7:11 AM,Analyst Name,Administrator,,,,,,,,,,,,,,
        elif splitted[0] == self.HEADERKEY_ANALYSISTIME:
            if splitted[1]:
                try:
                    d = datetime.strptime(splitted[1], "%m/%d/%Y %I:%M %p")
                    self._header[self.HEADERKEY_ANALYSISTIME] = d
                except ValueError:
                    self.err(_("Invalid Analysis Time format"), self._numline, line)
            else:
                self.warn(_("Analysis Time not found or empty"), self._numline, line)

            if splitted[2] and splitted[2] == self.HEADERKEY_ANALYSTNAME:
                if splitted[3]:
                    self._header[self.HEADERKEY_ANALYSTNAME] = splitted[3]
                else:
                    self.warn(_("Analyst Name not found or empty"), self._numline, line)
            else:
                self.err(_("Analyst Name not found"), self._numline, line)

        # Report Time,3/20/2013 7:12 AM,Reporter Name,Administrator,,,,,,,,,,,,,,
        elif splitted[0] == self.HEADERKEY_REPORTTIME:
            if splitted[1]:
                try:
                    d = datetime.strptime(splitted[1], "%m/%d/%Y %I:%M %p")
                    self._header[self.HEADERKEY_REPORTTIME] = d
                except ValueError:
                    self.err(_("Invalid Report Time format"), self._numline, line)
            else:
                self.warn(_("Report time not found or empty"), self._numline, line)

            if splitted[2] and splitted[2] == self.HEADERKEY_REPORTERNAME:
                if splitted[3]:
                    self._header[self.HEADERKEY_REPORTERNAME] = splitted[3]
                else:
                    self.warn(_("Reporter Name not found or empty"), self._numline, line)
            else:
                self.err(_("Reporter Name not found"), self._numline, line)

        # Last Calib Update,3/20/2013 7:11 AM,Batch State,Processed,,,,,,,,,,,,,,
        elif splitted[0] == self.HEADERKEY_LASTCALIBRATION:
            if splitted[1]:
                try:
                    d = datetime.strptime(splitted[1], "%m/%d/%Y %I:%M %p")
                    self._header[self.HEADERKEY_LASTCALIBRATION] = d
                except ValueError:
                    self.err(_("Invalid Last Calibration time format"), self._numline, line)
            else:
                self.warn(_("Last Calibration time not found or empty"), self._numline, line)

            if splitted[2] and splitted[2] == self.HEADERKEY_BATCHSTATE:
                if splitted[3]:
                    self._header[self.HEADERKEY_BATCHSTATE] = splitted[3]
                else:
                    self.warn(_("Batch state not found or empty"), self._numline, line)
            else:
                self.err(_("Batch state not found"), self._numline, line)

        return 0

    def parse_sequencetableline(self, line):
        """ Parses sequence table lines

            Sequence Table example:
            Sequence Table,,,,,,,,,,,,,,,,,
            Data File,Sample Name,Position,Inj Vol,Level,Sample Type,Acq Method File,,,,,,,,,,,
            prerunrespchk.d,prerunrespchk,Vial 3,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            DSS_Nist_L1.d,DSS_Nist_L1,P1-A2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            DSS_Nist_L2.d,DSS_Nist_L2,P1-B2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            DSS_Nist_L3.d,DSS_Nist_L3,P1-C2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            UTAK_DS_L1.d,UTAK_DS_L1,P1-D2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            UTAK_DS_L2.d,UTAK_DS_L2,P1-E2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            mid_respchk.d,mid_respchk,Vial 3,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            UTAK_DS_low.d,UTAK_DS_Low,P1-F2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            FDBS_31.d,FDBS_31,P1-G2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            FDBS_32.d,FDBS_32,P1-H2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            LS_60-r001.d,LS_60,P1-G12,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            LS_60-r002.d,LS_60,P1-G12,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            LS_61-r001.d,LS_61,P1-H12,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            LS_61-r002.d,LS_61,P1-H12,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            post_respchk.d,post_respchk,Vial 3,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            ,,,,,,,,,,,,,,,,,
        """

        # Sequence Table,,,,,,,,,,,,,,,,,
        # prerunrespchk.d,prerunrespchk,Vial 3,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
        # mid_respchk.d,mid_respchk,Vial 3,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
        # ,,,,,,,,,,,,,,,,,
        if line.startswith(self.SEQUENCETABLE_KEY) \
            or line.startswith(self.SEQUENCETABLE_PRERUN) \
            or line.startswith(self.SEQUENCETABLE_MIDRUN) \
            or self._end_sequencetable == True:

            # Nothing to do, continue
            return 0

        # Data File,Sample Name,Position,Inj Vol,Level,Sample Type,Acq Method File,,,,,,,,,,,
        if line.startswith(self.SEQUENCETABLE_HEADER_DATAFILE):
            self._sequencesheader = [token.strip() for token in line.split(',') if token.strip()]
            return 0

        # post_respchk.d,post_respchk,Vial 3,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
        # Quantitation Results,,,,,,,,,,,,,,,,,
        if line.startswith(self.SEQUENCETABLE_POSTRUN) \
            or line.startswith(self.QUANTITATIONRESULTS_KEY) \
            or line.startswith(self.COMMAS):
            self._end_sequencetable = True
            if len(self._sequences) == 0:
                self.err(_("No Sequence Table found"), self._numline)
                return -1

            # Jumps 2 lines:
            # Data File,Sample Name,Position,Inj Vol,Level,Sample Type,Acq Method File,,,,,,,,,,,
            # prerunrespchk.d,prerunrespchk,Vial 3,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
            return 2

        # DSS_Nist_L1.d,DSS_Nist_L1,P1-A2,-1.00,,Sample,120824_VitD_MAPTAD_1D_MRM_practice.m,,,,,,,,,,,
        splitted = [token.strip() for token in line.split(',')]
        sequence = {}
        for colname in self._sequencesheader:
            sequence[colname] = ''

        for i in range(len(splitted)):
            token = splitted[i]
            if i < len(self._sequencesheader):
                colname = self._sequencesheader[i]
                if token and colname in self.SEQUENCETABLE_NUMERICHEADERS:
                    try:
                        sequence[colname] = float(token)
                    except ValueError:
                        self.warn(_("No valid number %s in column %s (%s)") %
                                    (token, str(i+1), colname), self._numline, line)
                        sequence[colname] = token
                else:
                    sequence[colname] = token
            elif token:
                self.err(_("Orphan value in column %s (%s)") % (str(i+1), token),
                           self._numline, line)
        self._sequences.append(sequence)

    def parse_quantitationesultsline(self, line):
        """ Parses quantitation result lines

            Quantitation results example:
            Quantitation Results,,,,,,,,,,,,,,,,,
            Target Compound,25-OH D3+PTAD+MA,,,,,,,,,,,,,,,,
            Data File,Compound,ISTD,Resp,ISTD Resp,Resp Ratio, Final Conc,Exp Conc,Accuracy,,,,,,,,,
            prerunrespchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,5816,274638,0.0212,0.9145,,,,,,,,,,,
            DSS_Nist_L1.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,6103,139562,0.0437,1.6912,,,,,,,,,,,
            DSS_Nist_L2.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,11339,135726,0.0835,3.0510,,,,,,,,,,,
            DSS_Nist_L3.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,15871,141710,0.1120,4.0144,,,,,,,,,,,
            mid_respchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,4699,242798,0.0194,0.8514,,,,,,,,,,,
            DSS_Nist_L3-r002.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,15659,129490,0.1209,4.3157,,,,,,,,,,,
            UTAK_DS_L1-r001.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,29846,132264,0.2257,7.7965,,,,,,,,,,,
            UTAK_DS_L1-r002.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,28696,141614,0.2026,7.0387,,,,,,,,,,,
            post_respchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,5022,231748,0.0217,0.9315,,,,,,,,,,,
            ,,,,,,,,,,,,,,,,,
            Target Compound,25-OH D2+PTAD+MA,,,,,,,,,,,,,,,,
            Data File,Compound,ISTD,Resp,ISTD Resp,Resp Ratio, Final Conc,Exp Conc,Accuracy,,,,,,,,,
            prerunrespchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,6222,274638,0.0227,0.8835,,,,,,,,,,,
            DSS_Nist_L1.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,1252,139562,0.0090,0.7909,,,,,,,,,,,
            DSS_Nist_L2.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,3937,135726,0.0290,0.9265,,,,,,,,,,,
            DSS_Nist_L3.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,826,141710,0.0058,0.7697,,,,,,,,,,,
            mid_respchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,7864,242798,0.0324,0.9493,,,,,,,,,,,
            DSS_Nist_L3-r002.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,853,129490,0.0066,0.7748,,,,,,,,,,,
            UTAK_DS_L1-r001.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,127496,132264,0.9639,7.1558,,,,,,,,,,,
            UTAK_DS_L1-r002.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,135738,141614,0.9585,7.1201,,,,,,,,,,,
            post_respchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,6567,231748,0.0283,0.9219,,,,,,,,,,,
            ,,,,,,,,,,,,,,,,,
        """

        # Quantitation Results,,,,,,,,,,,,,,,,,
        # prerunrespchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,5816,274638,0.0212,0.9145,,,,,,,,,,,
        # mid_respchk.d,25-OH D3+PTAD+MA,25-OH D3d3+PTAD+MA,4699,242798,0.0194,0.8514,,,,,,,,,,,
        # post_respchk.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,6567,231748,0.0283,0.9219,,,,,,,,,,,
        # ,,,,,,,,,,,,,,,,,
        if line.startswith(self.QUANTITATIONRESULTS_KEY) \
            or line.startswith(self.QUANTITATIONRESULTS_PRERUN) \
            or line.startswith(self.QUANTITATIONRESULTS_MIDRUN) \
            or line.startswith(self.QUANTITATIONRESULTS_POSTRUN) \
            or line.startswith(self.COMMAS):

            # Nothing to do, continue
            return 0

        # Data File,Compound,ISTD,Resp,ISTD Resp,Resp Ratio, Final Conc,Exp Conc,Accuracy,,,,,,,,,
        if line.startswith(self.QUANTITATIONRESULTS_HEADER_DATAFILE):
            self._quantitationresultsheader = [token.strip() for token in line.split(',') if token.strip()]
            return 0

        # Target Compound,25-OH D3+PTAD+MA,,,,,,,,,,,,,,,,
        if line.startswith(self.QUANTITATIONRESULTS_TARGETCOMPOUND):
            # New set of Quantitation Results
            splitted = [token.strip() for token in line.split(',')]
            if not splitted[1]:
                self.warn(_("No Target Compound found"), self._numline, line)
            return 0

        # DSS_Nist_L1.d,25-OH D2+PTAD+MA,25-OH D3d3+PTAD+MA,1252,139562,0.0090,0.7909,,,,,,,,,,,
        splitted = [token.strip() for token in line.split(',')]
        quantitation = {}
        for colname in self._quantitationresultsheader:
            quantitation[colname] = ''

        for i in range(len(splitted)):
            token = splitted[i]
            if i < len(self._quantitationresultsheader):
                colname = self._quantitationresultsheader[i]
                if token and colname in self.QUANTITATIONRESULTS_NUMERICHEADERS:
                    try:
                        quantitation[colname] = float(token)
                    except ValueError:
                        self.warn(_("No valid number %s in column %s (%s)") %
                                    (token, str(i+1), colname), self._numline, line)
                        quantitation[colname] = token
                else:
                    quantitation[colname] = token
            elif token:
                self.err(_("Orphan value in column %s (%s)") % (str(i+1), token),
                           self._numline, line)

        if self.QUANTITATIONRESULTS_COMPOUNDCOLUMN in quantitation:
            compound = quantitation[self.QUANTITATIONRESULTS_COMPOUNDCOLUMN]

            # Look for sequence matches and populate rawdata
            datafile = quantitation.get(self.QUANTITATIONRESULTS_HEADER_DATAFILE, '')
            if not datafile:
                self.err(_("No Data File found for quantitation result"), self.num_line, line)
            else:
                seqs = [sequence for sequence in self._sequences \
                        if sequence.get('Data File', '') == datafile]
                if len(seqs) == 0:
                    self.err(_("No sample found for quntitative result %s") % datafile, self.num_line, line)
                elif len(seqs) > 1:
                    self.err(_("More than one sequence found for quantitative result %s") % datafile, self._numline, line)
                else:
                    objid = seqs[0].get(self.SEQUENCETABLE_HEADER_SAMPLENAME, '')
                    if objid:
                        quantitation['DefaultResult'] = 'Final Conc'
                        quantitation['Remarks'] = _("Autoimport")
                        raw = self.getRawResults().get(objid, {})
                        raw[compound] = quantitation
                        self._addRawResult(objid, raw, True)
                    else:
                        self.err(_("No valid sequence for %s " % datafile, self._numline, line))
        else:
            self.err(_("Value for column '%s' not found") \
                     % self.QUANTITATIONRESULTS_COMPOUNDCOLUMN,
                     self._numline, line)


class MasshunterQuantImporter(AnalysisResultsImporter):

    def __init__(self, parser, context, idsearchcriteria, override,
                 allowed_ar_states=None, allowed_analysis_states=None):
        AnalysisResultsImporter.__init__(self, parser, context, idsearchcriteria,
                                         override, allowed_ar_states,
                                         allowed_analysis_states)
