"""
Permanent revision history for zwiki pages.

Warning: this implementation might be zodb-cache-unfriendly as revisions
increase.
"""

from AccessControl import getSecurityManager, ClassSecurityInfo
from Globals import InitializeClass
try:    from Products.BTreeFolder2.BTreeFolder2 import BTreeFolder2 as Folder
except: from OFS.Folder import Folder # zope 2.7

import re
import Permissions
from OutlineSupport import PersistentOutline

class PageHistorySupport:
    """
    This mixin provides methods to save, browse and restore zwiki page
    revisions.  Unlike zope's built-in transaction history, these are
    saved forever, as page objects in a revisions subfolder.  Individual
    revisions may be deleted manually without ill effect.

    The methods below should generally work whether they are called on the
    latest revision (in the wiki folder), or on an older revision (in the
    revisions subfolder), except where noted.
    """
    security = ClassSecurityInfo()

    def ensureRevisionsFolder(self):
        if self.revisionsFolder() is None:
            self.folder()._setObject('revisions',Folder('revisions'))

    def inRevisionsFolder(self):
        return self.folder().getId() == 'revisions'

    def revisionsFolder(self):
        """Get the revisions subfolder, even called from within it."""
        if self.inRevisionsFolder():
            return self.folder()
        elif hasattr(self.folder().aq_base, 'revisions'):
            f = self.folder().revisions
            if f.isPrincipiaFolderish:
                return f
        return None
            
    def wikiFolder(self):
        """Get the main wiki folder, even if called on a revision object."""
        if self.inRevisionsFolder():
            f = self.folder()
            # like folder()
            return getattr(getattr(f,'aq_inner',f),'aq_parent',None)
        else:
            return self.folder()

    security.declareProtected(Permissions.View, 'revisions')
    def revisions(self):
        """
        Get a list of this page's revisions, oldest first.
        
        A page's revisions are all the page objects with the same root id
        plus a possible dot-number suffix. The one with no suffix is the
        latest revision, kept in the main wiki folder; older revisions
        have a suffix and are kept in the revisions subfolder.
        """
        return self.oldRevisions() + [self.latestRevision()]

    def latestRevision(self):
        return self.wikiFolder()[self.getIdBase()]

    def oldRevisions(self):
        f = self.revisionsFolder()
        if not f:
            return []
        else:
            isrev = re.compile(r'%s\.\d+$' % self.getIdBase()).match
            ids = filter(isrev, f.objectIds(spec=self.meta_type))
            # probably in the right order, but let's make sure
            ids.sort(lambda a,b: cmp(int(a.split('.')[1]), int(b.split('.')[1])))
            return [f[id] for id in ids]

    def getIdBase(self):
        """This page's id with any revision number suffix removed."""
        return re.sub(r'^(.*)\.\d+$', r'\1', self.getId())

    security.declareProtected(Permissions.View, 'revisionCount')
    def revisionCount(self):
        """The number of revisions existing for this page."""
        return len(self.revisions())

    security.declareProtected(Permissions.View, 'revision')
    def revision(self, rev):
        """Get the specified revision of this page object (starting from 1)."""
        if rev:
            # should be no more than one, but you never know
            revs = [r for r in self.revisions() if r.revisionNumber()==rev]
            if revs: return revs[0]
        return None

    security.declareProtected(Permissions.View, 'previousRevision')
    def previousRevision(self):
        """Get the oldest saved revision of this page previous to this one."""
        r = self.previousRevisionNumber()
        if r: return self.revision(r)
        else: return None

    security.declareProtected(Permissions.View, 'nextRevision')
    def nextRevision(self):
        """Get the next saved revision of this page after this one."""
        r = self.nextRevisionNumber()
        if r: return self.revision(r)
        else: return None

    security.declareProtected(Permissions.View, 'revisionNumber')
    def revisionNumber(self):
        """Get this page's revision number."""
        return getattr(self.aq_base,'revision_number',1)

    def revisionNumberFromId(self):
        m = re.search(r'\.(\d+)$',self.getId())
        if m: return int(m.group(1))
        else: return None

    def revisionNumbers(self):
        return [r.revisionNumber() for r in self.revisions()]

    def firstRevisionNumber(self):
        """The revision number of the earliest saved revision of this page."""
        return self.revisionNumbers()[0]

    def lastRevisionNumber(self):
        """The revision number of the latest saved revision of this page."""
        return self.revisionNumbers()[-1]

    def previousRevisionNumber(self):
        """The number of the latest saved revision before this one, or None."""
        revnos = self.revisionNumbers()
        i = revnos.index(self.revisionNumber())
        if i: return revnos[i-1]
        else: return None

    def nextRevisionNumber(self):
        """The number of the next saved revision after this one, or None."""
        revnos = self.revisionNumbers()
        i = revnos.index(self.revisionNumber())
        if i < len(revnos)-1: return revnos[i+1]
        else: return None

    def revisionNumberBefore(self, username):
        """The revision number of the last edit not by username, or None."""
        for r in range(self.revisionCount(),0,-1):
            if self.revision(r).last_editor != username:
                return r
        return None

    def saveRevision(self, REQUEST=None):
        """
        Copy this page to the revisions folder and increment its revision no.

        Will (should) not work if called on an old revision.
        """
        self.ensureRevisionsFolder()
        rid = '%s.%d' % (self.getId(), self.revisionNumber())
        ob = self._getCopy(self.folder())
        ob._setId(rid)

        # kludge so the following won't update a catalog or outline cache
        # in the revisions folder (hopefully thread-safe, oherwise
        # escalate to "horrible kludge"):
        manage_afterAdd                = self.__class__.manage_afterAdd
        wikiOutline                    = self.__class__.wikiOutline
        self.__class__.manage_afterAdd = lambda self,item,container:None
        self.__class__.wikiOutline     = lambda self:PersistentOutline()

        self.revisionsFolder()._setObject(rid, ob)

        # end kludge
        self.__class__.manage_afterAdd = manage_afterAdd
        self.__class__.wikiOutline     = wikiOutline

        # and increment
        self.revision_number = self.revisionNumber() + 1

    # backwards compatibility / temporary

    def forwardRev(self,rev): return self.revisionCount() - rev - 1

    def lastlog(self, rev=0, withQuotes=0):
        """
        Get the log note from an earlier revision of this page.

        Just a quick helper for diff browsing.
        """
        rev = self.forwardRev(int(rev))
        note = self.revisions()[rev].lastLog()
        match = re.search(r'"(.*)"',note)
        if match:
            if withQuotes: return match.group()
            else: return match.group(1)
        else:
            return ''

InitializeClass(PageHistorySupport)

