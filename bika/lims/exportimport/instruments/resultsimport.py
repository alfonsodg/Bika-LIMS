from Products.CMFCore.utils import getToolByName
from bika.lims import bikaMessageFactory as _
from bika.lims.exportimport.instruments.logger import Logger
from bika.lims.idserver import renameAfterCreation
from bika.lims.utils import tmpID


class InstrumentResultsFileParser(Logger):

    def __init__(self, infile, mimetype):
        Logger.__init__(self)
        self._infile = infile
        self._header = {}
        self._rawresults = {}
        self._mimetype = mimetype

    def getInputFile(self):
        """ Returns the results input file
        """
        return self._infile

    def parse(self):
        """ Parses the input results file and populates the rawresults dict.
            See getRawResults() method for more info about rawresults format
            Returns True if the file has been parsed successfully.
            Is highly recommended to use _addRawResult method when adding
            raw results.
            IMPORTANT: To be implemented by child classes
        """
        raise NotImplementedError

    def getAttachmentFileType(self):
        """ Returns the file type name that will be used when creating the
            AttachmentType used by the importer for saving the results file as
            an attachment in each Analysis matched.
            By default returns self.getFileMimeType()
        """
        return self.getFileMimeType()

    def getFileMimeType(self):
        """ Returns the results file type
        """
        return self._mimetype

    def getHeader(self):
        """ Returns a dictionary with custom key, values
        """
        return self._header

    def _addRawResult(self, resid, values={}, override=False):
        """ Adds a set of raw results for an object with id=resid
            resid is usually an Analysis Request ID or Worksheet's Reference
            Analysis ID. The values are a dictionary in which the keys are
            analysis service keywords and the values, another dictionary with
            the key,value results.
            The column 'DefaultResult' must be provided, because is used to map
            to the column from which the default result must be retrieved.

            Example:
            resid  = 'DU13162-001-R1'
            values = {
                'D2': {'DefaultResult': 'Final Conc',
                       'Remarks':       '',
                       'Resp':          '5816',
                       'ISTD Resp':     '274638',
                       'Resp Ratio':    '0.0212',
                       'Final Conc':    '0.9145',
                       'Exp Conc':      '1.9531',
                       'Accuracy':      '98.19' },

                'D3': {'DefaultResult': 'Final Conc',
                       'Remarks':       '',
                       'Resp':          '5816',
                       'ISTD Resp':     '274638',
                       'Resp Ratio':    '0.0212',
                       'Final Conc':    '0.9145',
                       'Exp Conc':      '1.9531',
                       'Accuracy':      '98.19' }
                }
        """
        if override == True or resid not in self._rawresults.keys():
            self._rawresults[resid] = values

    def getObjectsTotalCount(self):
        """ The total number of objects (ARs, ReferenceSamples, etc.) parsed
        """
        return len(self.getRawResults())

    def getResultsTotalCount(self):
        """ The total number of analysis results parsed
        """
        count = 0
        for val in self.getRawResults().values():
            count += len(val)
        return count

    def getAnalysesTotalCount(self):
        """ The total number of different analyses parsed
        """
        return len(self.getAnalysisKeywords())

    def getAnalysisKeywords(self):
        """ The analysis service keywords found
        """
        analyses = []
        for val in self.getRawResults().values():
            for key in val.keys():
                if key not in analyses:
                    analyses.append(key)
        return analyses

    def getRawResults(self):
        """ Returns a dictionary containing the parsed results data
            Each dict key is the results row ID (usually AR ID or Worksheet's
            Reference Sample ID). Each item is another dictionary, in which the
            key is a the AS Keyword.
            Inside the AS dict, the column 'DefaultResult' must be
            provided, that maps to the column from which the default
            result must be retrieved.
            If 'Remarks' column is found, it value will be set in Analysis
            Remarks field when using the deault Importer.

            Example:
            raw_results['DU13162-001-R1'] = {

                'D2': {'DefaultResult': 'Final Conc',
                       'Remarks':       '',
                       'Resp':          '5816',
                       'ISTD Resp':     '274638',
                       'Resp Ratio':    '0.0212',
                       'Final Conc':    '0.9145',
                       'Exp Conc':      '1.9531',
                       'Accuracy':      '98.19' },

                'D3': {'DefaultResult': 'Final Conc',
                       'Remarks':       '',
                       'Resp':          '5816',
                       'ISTD Resp':     '274638',
                       'Resp Ratio':    '0.0212',
                       'Final Conc':    '0.9145',
                       'Exp Conc':      '1.9531',
                       'Accuracy':      '98.19' }

            in which:
            - 'DU13162-001-R1' is the Analysis Request ID,
            - 'D2' column is an analysis service keyword,
            - 'DefaultResult' column maps to the column with default result
            - 'Remarks' column with Remarks results for that Analysis
            - The rest of the dict columns are results (or additional info)
              that can be set to the analysis if needed (the default importer 
              will look for them if the analysis has Interim fields).

            In the case of reference samples:
            Control/Blank:
            raw_results['QC13-0001-0002'] = {...}

            Duplicate of sample DU13162-009 (from AR DU13162-009-R1)
            raw_results['QC-DU13162-009-002'] = {...}

        """
        return self._rawresults


class InstrumentCSVResultsFileParser(InstrumentResultsFileParser):

    def __init__(self, infile):
        InstrumentResultsFileParser.__init__(self, infile, 'CSV')

    def parse(self):
        infile = self.getInputFile()
        self.log(_("Parsing file ") + " %s (%s)" % (infile.filename,
                                                    infile.name))
        jump = 0
        for line in infile.readlines():
            self._numline += 1
            if jump == -1:
                # Something went wrong. Finish
                self.err(_("File processing finished due to critical errors"))
                return False
            if jump > 0:
                # Jump some lines
                jump -= 1
                continue

            if not line or not line.strip():
                continue

            line = line.strip()
            jump = self._parseline(line)

        if len(self.getRawResults()) == 0:
            self.err(_("No results found"))
            return False

        self.log(_("End of file reached successfully: %s objects, "
                   "%s analyses, %s results") %
                 (str(self.getObjectsTotalCount()),
                  str(self.getAnalysesTotalCount()),
                  str(self.getResultsTotalCount())))
        return True

    def _parseline(self, line):
        """ Parses a line from the input CSV file and populates rawresults
            (look at getRawResults comment)
            returns -1 if critical error found and parser must end
            returns the number of lines to be jumped in next read. If 0, the
            parser reads the next line as usual
        """
        raise NotImplementedError


class AnalysisResultsImporter(Logger):

    def __init__(self, parser, context, 
                 idsearchcriteria=None,
                 override=[False, False],
                 allowed_ar_states=None,
                 allowed_analysis_states=None):
        Logger.__init__(self)
        self._parser = parser
        self.context = context
        self._allowed_ar_states = allowed_ar_states
        self._allowed_analysis_states = allowed_analysis_states
        self._override = override
        self._idsearch = idsearchcriteria
        self.bsc = getToolByName(self.context, 'bika_setup_catalog')
        self.bac = getToolByName(self.context, 'bika_analysis_catalog')
        self.pc = getToolByName(self.context, 'portal_catalog')
        self.bc = getToolByName(self.context, 'bika_catalog')
        self.wf = getToolByName(self.context, 'portal_workflow')
        if not self._allowed_ar_states:
            self._allowed_ar_states=['sample_received',
                                     'attachment_due',
                                     'to_be_verified']
        if not self._allowed_analysis_states:
            self._allowed_analysis_states=['sampled',
                                           'sample_received',
                                           'attachment_due',
                                           'to_be_verified']
        if not self._idsearch:
            self._idsearch=['getRequestID']

    def getParser(self):
        """ Returns the parser that will be used for the importer
        """
        return self._parser

    def getAllowedARStates(self):
        """ The allowed Analysis Request states
            The results import will only take into account the analyses
            contained inside an Analysis Request which current state is one
            from these.
        """
        return self._allowed_ar_states

    def getAllowedAnalysisStates(self):
        """ The allowed Analysis states
            The results import will only take into account the analyses
            if its current state is in the allowed analysis states.
        """
        return self._allowed_analysis_states

    def getOverride(self):
        """ If the importer must override previously entered results.
            [False, False]: The results will not be overriden
            [True, False]: The results will be overriden only if there's no
                           result entered yet,
            [True, True]: The results will be always overriden, also if the
                          parsed result is empty.
        """
        return self._override

    def getIdSearchCriteria(self):
        """ Returns the search criteria for retrieving analyses.
            Example: 
            serachcriteria=['getRequestID', 'getSampleID', 'getClientSampleID']
        """
        return self._idsearch

    def process(self):
        parsed = self._parser.parse()
        if parsed == False:
            return False

        self._errors = self._parser.errors
        self._logs = self._parser.logs

        # Allowed analysis states
        allowed_ar_states_msg = [_(s) for s in self.getAllowedARStates()]
        allowed_an_states_msg = [_(s) for s in self.getAllowedAnalysisStates()]
        self.log(_("Allowed Analysis Request states: %s") % (', '.join(allowed_ar_states_msg)))
        self.log(_("Allowed analysis states: %s") % (', '.join(allowed_an_states_msg)))

        # Exclude non existing ACODEs
        acodes = []
        ancount = 0
        arprocessed = []
        importedars = {}
        rawacodes = self._parser.getAnalysisKeywords()
        for acode in rawacodes:
            service = self.bsc(getKeyword=acode)
            if not service:
                self.err(_('Service keyword %s not found') % acode)
            else:
                acodes.append(acode)

        for objid, results in self._parser.getRawResults().iteritems():
            analyses = self._getZODBAnalyses(objid)
            if len(analyses) == 0:
                continue
            for acode, values in results.iteritems():
                if acode not in acodes:
                    # Analysis keyword doesn't exist
                    continue

                ans = [analysis for analysis in analyses \
                       if analysis.getKeyword() == acode]

                if len(ans) > 1:
                    self.err(_("More than one analysis found for %s and %s") %
                             (objid, acode))
                    continue

                elif len(ans) == 0:
                    self.err(_("No analyses found for %s and %s") %
                             (objid, acode))
                    continue

                analysis = ans[0]
                processed = self._process_analysis(objid, analysis, values)
                if processed:
                    ancount += 1

                    ar = analysis.portal_type == 'Analysis' and analysis.aq_parent or None
                    if ar and ar.UID:
                        # Set AR imported info
                        arprocessed.append(ar.UID())
                        importedar = ar.getRequestID() in importedars.keys() \
                                    and importedars[ar.getRequestID()] or []
                        if acode not in importedar:
                            importedar.append(acode)
                        importedars[ar.getRequestID()] = importedar

                    # Create the AttachmentType for mime type if not exists
                    attuid = None
                    attachmentType = self.bsc(portal_type="AttachmentType",
                                              title=self._parser.getAttachmentFileType())
                    if len(attachmentType) == 0:
                        try:
                            folder = self.context.bika_setup.bika_attachmenttypes
                            _id = folder.invokeFactory('AttachmentType', id=tmpID())
                            obj = folder[_id]
                            obj.edit(title=self._parser.getAttachmentFileType(),
                                     description="Autogenerated file type")
                            obj.unmarkCreationFlag()
                            renameAfterCreation(obj)
                            attuid = obj.UID()
                        except:
                            attuid = None
                            self.err(_("Unable to create the Attachment Type %s ") % self._parser.getFileMimeType())
                    else:
                        attuid = attachmentType[0].UID

                    if attuid is not None:
                        try:
                            # Attach the file to the Analysis
                            wss = analysis.getBackReferences('WorksheetAnalysis')
                            if wss and len(wss) > 0:
                                ws = wss[0]
                                attachmentid = ws.invokeFactory("Attachment", id=tmpID())
                                attachment = ws._getOb(attachmentid)
                                attachment.edit(
                                    AttachmentFile=self._parser.getInputFile(),
                                    AttachmentType=attuid,
                                    AttachmentKeys='Results, Automatic import')
                                attachment.reindexObject()
                                others = analysis.getAttachment()
                                attachments = []
                                for other in others:
                                    if other.getAttachmentFile().filename != attachment.getAttachmentFile().filename:
                                        attachments.append(other.UID())
                                attachments.append(attachment.UID())
                                analysis.setAttachment(attachments)
                        except:
#                            self.err(_("Unable to attach results file '%s' to AR %s") %
#                                     (self._parser.getInputFile().filename,
#                                      ar.getRequestID()))
                            pass

        # Calculate analysis dependencies
        for aruid in arprocessed:
            ar = self.bc(portal_type='AnalysisRequest',
                         UID=aruid)
            ar = ar[0].getObject()
            analyses = ar.getAnalyses()
            for analysis in analyses:
                analysis = analysis.getObject()
                if (analysis.calculateResult(True, True)):
                    self.log(_("%s calculated result for '%s': '%s'") %
                         (ar.getRequestID(), analysis.getKeyword(), str(analysis.getResult())))

        for arid, acodes in importedars.iteritems():
            acodesmsg = ["Analysis %s" % acod for acod in acodes]
            msg = "%s: %s %s" % (arid, ", ".join(acodesmsg), "imported sucessfully")
            self.log(msg)

        self.log(_("Import finished successfully: %s ARs and %s results updated") %
                 (str(len(importedars)), str(ancount)))

    def _getZODBAnalyses(self, objid):
        """ Searches for analyses from ZODB to be filled with results.
            objid can be either AR ID or Worksheet's Reference Sample IDs.
            It uses the getIdSearchCriteria() for searches
            Only analyses that matches with getAnallowedAnalysisStates() will
            be returned. If not a ReferenceAnalysis, getAllowedARStates() is
            also checked.
            Returns empty array if no analyses found
        """
        ars = []
        analyses = []
        searchcriteria = self.getIdSearchCriteria()
        allowed_ar_states = self.getAllowedARStates()
        allowed_an_states = self.getAllowedAnalysisStates()
        allowed_ar_states_msg = [_(s) for s in allowed_ar_states]
        allowed_an_states_msg = [_(s) for s in allowed_an_states]
        if 'getRequestID' in searchcriteria:
            ars = self.bc(portal_type='AnalysisRequest',
                          getRequestID=objid,
                          review_state=allowed_ar_states)

        if len(ars) == 0 and 'getSampleID' in searchcriteria:
            ars = self.bc(portal_type='AnalysisRequest',
                          getSampleID=objid,
                          review_state=allowed_ar_states)

        if len(ars) == 0 and 'getClientSampleID' in searchcriteria:
            ars = self.bc(portal_type='AnalysisRequest',
                          getClientSampleID=objid,
                          review_state=allowed_ar_states)

        if len(ars) == 0 and 'getRequestID' in searchcriteria:
            ars = self.bc(portal_type='AnalysisRequest',
                        UID=objid,
                        review_state=allowed_ar_states)

        if len(ars) == 0:
            # Look for QC Analyses
            refans = self.bac(portal_type=['ReferenceAnalysis',
                                           'DuplicateAnalysis'],
                                getReferenceAnalysesGroupID=objid)

            if len(refans) == 0:
                refans = self.bac(portal_type=['ReferenceAnalysis',
                                               'DuplicateAnalysis'], id=objid)
                if len(refans) == 0:
                    refans = self.bac(portal_type=['ReferenceAnalysis',
                                                   'DuplicateAnalysis'], UID=objid)

                if len(refans) == 0:
                    self.err(_("No Analysis Request with '%s' states neither QC"
                               " analyses found for %s") %
                             (', '.join(allowed_ar_states_msg), objid))
                    return []

                else:
                    an = refans[0].getObject()
                    wss = an.getBackReferences('WorksheetAnalysis')
                    if wss and len(wss) > 0:
                        analyses = [an for an in wss.getAnalyses() \
                                    if (an.portal_type == 'ReferenceAnalysis' \
                                        or an.portal_type == 'DuplicateAnalysis')
                                    and an.getReferenceAnalysesGroupID() \
                                        == refans.getReferenceAnalysesGroupID()]
                    else:
                        analyses = [an.getObject() for an in refans]
            else:
                analyses = [an.getObject() for an in refans]

        else:
            if len(ars) > 1:
                self.err(_("More than one Analysis Request found for %s") % objid)
                return []

            else:
                ar = ars[0].getObject()
                analyses = [analysis.getObject() for analysis in ar.getAnalyses()]

        # Discard analyses that don't match with allowed_an_states
        analyses = [analysis for analysis in analyses \
                    if analysis.portal_type != 'Analysis' \
                        or self.wf.getInfoFor(analysis, 'review_state') \
                        in allowed_an_states]

        if len(analyses) == 0:
            self.err(_("No analyses '%s' states found for %s") %
                     (', '.join(allowed_an_states_msg), objid))

        return analyses

    def _process_analysis(self, objid, analysis, values):
        resultsaved = False
        acode = analysis.getKeyword()
        defresultkey = values.get("DefaultResult", "")
        interimsout = []
        interims = hasattr(analysis, 'getInterimFields') \
                    and analysis.getInterimFields() or []
        for interim in interims:
            keyword = interim['keyword']
            title = interim['title']
            if values.get(keyword, '') or values.get(keyword, '') == 0:
                res = values.get(keyword)
                self.log(_("%s result for '%s:%s': '%s'") %
                         (objid, acode, keyword, str(res)))
                ninterim = interim
                ninterim['value'] = res
                interimsout.append(ninterim)
                resultsaved = True
#                interimsout.append({'keyword': interim['keyword'],
#                                    'value': res})
#                if keyword == defresultkey:
#                    resultsaved = True
            elif values.get(title, '') or values.get(title, '') == 0:
                res = values.get(title)
                self.log(_("%s result for '%s:%s': '%s'") %
                         (objid, acode, title, str(res)))
                ninterim = interim
                ninterim['value'] = res
                interimsout.append(ninterim)
                resultsaved = True
#                interimsout.append({'keyword': interim['keyword'],
#                                    'value': res})
#                if keyword == defresultkey:
#                    resultsaved = True
            else:
                interimsout.append(interim)

        if len(interimsout) > 0:
            analysis.setInterimFields(interimsout)

        if resultsaved == False and (values.get(defresultkey, '') \
                                     or values.get(defresultkey, '') == 0 \
                                     or self._override[1] == True):
            # set the result
            res = values.get(defresultkey, '')
            self.log(_("%s result for '%s': '%s'") % (objid, acode, str(res)))
            analysis.setResult(res)
            resultsaved = True

        elif resultsaved == False:
            self.warn(_("%s result for '%s': Empty") % (objid, acode))

#        if (resultsaved or len(interimsout) > 0) \
#            and values.get('Remarks', '') \
#            and analysis.portal_type == 'Analysis':
#            analysis.setRemarks(values['Remarks'])

        return resultsaved or len(interimsout) > 0
