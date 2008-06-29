import time
import urllib
import socket
from xml.dom import minidom

from twisted.web import http
from twisted.web import static
from twisted.web import resource

import txlb
from txlb.admin import css
from txlb.admin import template


class UnauthorizedResource(resource.Resource):
    """
    The page resource to present when a restricted resource is requested, thus
    prompting the user with a basic auth dialog.
    """
    isLeaf = 1
    unauthorizedPage = static.Data(template.unauth, 'text/html')

    def render(self, request):
        request.setResponseCode(http.UNAUTHORIZED)
        request.setHeader(
            'WWW-authenticate', 'basic realm="PyDirector"')
        return self.unauthorizedPage.render(request)


class StyleSheet(resource.Resource):
    """
    The resource that serves the CSS.
    """
    def render_GET(self, request):
        """

        """
        return css.adminCSS


class BasePage(resource.Resource):
    """
    All resources that render the basic look and feel of the admin UI subclass
    this page class.
    """
    def __init__(self, parent):
        resource.Resource.__init__(self)
        self.parent = parent

    def getHeader(self, refreshURL=''):
        """

        """
        refresh = ''
        if refreshURL:
            refresh = template.refresh % (
                self.parent.conf.admin.refresh, refreshURL)
        return template.header % (
            txlb.name, refresh, txlb.name, self.parent.serverVersion,
            socket.gethostname())

    def getBody(self):
        """
        Subclasses must override this.
        """
        raise NotImplemented

    def getFooter(self, message=''):
        """

        """
        if message:
            message = template.message % urllib.unquote(message)
        return template.footer % (txlb.projectURL, txlb.name, message)


    def getPage(self):
        """
        Subclasses must override this.
        """
        raise NotImplemented

    def render_GET(self, request):
        """

        """
        return str(self.getPage(request))


class RunningPage(BasePage):
    """
    This class is responsible for presenting the admin UI, in all of it's data
    and button-pushing glory.
    """
    def getPage(self, request):
        """
        Don't look at me; this craziness is a modified version of the original.
        """
        verbose = False
        resultMessage = ''
        content = ''
        if request.args.has_key('refresh'):
            refresh = bool(request.args['refresh'][0])
            url = '/running?refresh=1&ignore=%s' % time.time()
            content += self.getHeader(refreshURL=url)
            stopStart = template.stopRefresh % time.time()
        else:
            content += self.getHeader()
            stopStart = template.startRefresh % time.time()
        content += template.refreshButtons % (
            time.ctime(time.time()), time.time(), stopStart)
        for service in self.parent.conf.getServices():
            # we don't want the configured listener here, we want the one that
            # is actually running. The best place to get that is from the
            # director
            # XXX we probably want to put this into a class method
            content += template.serviceName % service.name
            for index, l in enumerate(service.listen):
                proxy = self.parent.director.getProxy(service.name, index)
                hostPort = "%s:%s" % (proxy.host, proxy.port)
                content += template.listeningService % hostPort
            eg = service.getEnabledGroup()
            groups = service.getGroups()
            for group in groups:
                tracker = self.parent.director.getTracker(
                    service.name, group.name)
                stats = tracker.getStats()
                hdict = tracker.getHostNames()
                if group is eg:
                    klass = 'enabled'
                    desc = template.groupDescEnabled
                else:
                    klass = 'inactive'
                    desc = template.groupDescDisabled % (
                        service.name, group.name)
                content += template.groupName % (klass, group.name)
                content += desc
                content += template.groupHeaderForm % (
                    service.name, group.name, klass)
                counts = stats['openconns']
                failed = stats['failed']
                totals = stats['totals']
                k = counts.keys()
                k.sort()
                for h in k:
                    f = 0
                    if failed.has_key(h):
                        f = failed[h]
                    if counts.has_key(h):
                        oc = counts[h]
                    else:
                        oc = '--'
                    if totals.has_key(h):
                        tc = totals[h]
                    else:
                        tc = '--'
                    content += template.hostInfo % (
                        klass, hdict[h], h, oc, tc, f,
                        urllib.quote(service.name), urllib.quote(group.name),
                        urllib.quote(h))
                bad = stats['bad']
                if bad:
                    content += template.badHostGroup % klass
                for k in bad.keys():
                    host = '%s:%s' % k
                    when, what = bad[k]
                    content += template.badHostInfo % (
                        klass, hdict[host], host, what.getErrorMessage())
            content += template.serviceClose
        content += self.getFooter(resultMessage)
        return content


class RunningReadOnlyPage(BasePage):
    """
    A version of the RunningPage that disables write functionality. This is
    useful for non-atomic operations are taking place, decreasing the chances
    for the user to create race conditions.
    """


class RunningConfig(BasePage):
    """
    This class renders the in-memory configuration as XML.
    """
    def getPage(self, request):
        """

        """
        request.setHeader('Content-type', 'text/plain')
        verbose = False
        conf = self.parent.conf
        doc = minidom.Document()
        top = doc.createElement("pdconfig")
        doc.appendChild(top)
        for service in conf.getServices():
            top.appendChild(doc.createTextNode("\n    "))
            serv = doc.createElement("service")
            serv.setAttribute('name', service.name)
            top.appendChild(serv)
            # XXX
            # listening ports need to come from the running proxies in the
            # proxy manager, not from the configuration
            for l in service.listen:
                serv.appendChild(doc.createTextNode("\n        "))
                lobj = doc.createElement("listen")
                lobj.setAttribute('ip', l)
                serv.appendChild(lobj)
            groups = service.getGroups()
            for group in groups:
                serv.appendChild(doc.createTextNode("\n        "))
                tracker = self.parent.director.getTracker(service.name, group.name)
                xg = doc.createElement("group")
                xg.setAttribute('name', group.name)
                xg.setAttribute('scheduler', tracker.scheduler.schedulerName)
                serv.appendChild(xg)
                stats = tracker.getStats()
                hosts = group.getHosts()
                hdict = tracker.getHostNames()
                counts = stats['openconns']
                ahosts = counts.keys() # ahosts is now a list of active hosts
                # now add disabled hosts.
                for k in stats['bad'].keys():
                    ahosts.append('%s:%s'%k)
                ahosts.sort()
                for h in ahosts:
                    xg.appendChild(doc.createTextNode("\n            "))
                    xh = doc.createElement("host")
                    xh.setAttribute('name', hdict[h])
                    xh.setAttribute('ip', h)
                    xg.appendChild(xh)
                xg.appendChild(doc.createTextNode("\n        "))
            serv.appendChild(doc.createTextNode("\n        "))
            eg = service.getEnabledGroup()
            xeg = doc.createElement("enable")
            xeg.setAttribute("group", eg.name)
            serv.appendChild(xeg)
            serv.appendChild(doc.createTextNode("\n    "))
        top.appendChild(doc.createTextNode("\n    "))
        # now the admin block
        # XXX the configuration for the admin section has changed quite a bit,
        # and the following code needs to be updated to bring them into sync
        admin = self.parent.conf.admin
        if admin is not None:
            xa = doc.createElement("admin")
            # add the web
            xa.setAttribute("listen", "%s:%s"%admin.listen)
            top.appendChild(xa)
            for user in admin.getUsers():
                xa.appendChild(doc.createTextNode("\n        "))
                xu = doc.createElement("user")
                xu.setAttribute("name", user.name)
                xu.setAttribute("password", user.password)
                xu.setAttribute("access", user.access)
                xa.appendChild(xu)
            xa.appendChild(doc.createTextNode("\n    "))
            top.appendChild(doc.createTextNode("\n    "))
        # finally, the logging section (if set)
        #if logger.logfile is not None:
        #    xl = doc.createElement("logging")
        #    xl.setAttribute("file", logger.logfile)
        #    top.appendChild(xl)
        # final newline
        top.appendChild(doc.createTextNode("\n"))
        # and spit out the XML
        return doc.toxml()


class StoredConfig(BasePage):
    """
    This page renders the on-disk XML configuration file.
    """
    def getPage(self, request):
        """

        """
        request.setHeader('Content-type', 'text/plain')
        return self.parent.conf.dom.toxml()


class DeleteHost(BasePage):
    """
    This page is responsible for removing a host from rotation in the admin UI.
    It also updates the tracker and pulls the host out of rotation there as
    well.
    """
    def getPage(self, request):
        """

        """
        service = request.args['service'][0]
        group = request.args['group'][0]
        ip = request.args['ip'][0]
        tracker = self.parent.director.getTracker(
            serviceName=service, groupName=group)
        service = self.parent.conf.getService(service)
        eg = service.getEnabledGroup()
        if group == eg.name:
            if tracker.delHost(ip=ip, activegroup=1):
                msg = 'host %s deleted (from active group!)' % ip
            else:
                msg = 'host %s <b>not</b> deleted from active group' % ip
        else:
            if tracker.delHost(ip=ip):
                msg = 'host %s deleted from inactive group' % ip
            else:
                msg = 'host %s <b>not</b> deleted from inactive group' % ip
        request.redirect('/running?resultMessage=%s' % urllib.quote(msg))
        return "OK"


class AddHost(BasePage):
    """
    This page class is responsible for handling the "add page" action that puts
    new hosts into rotation, both in the admin UI as well as in the host
    tracking object.
    """
    def getPage(self, request):
        """

        """
        service = request.args['service'][0]
        group = request.args['group'][0]
        name = request.args['name'][0]
        ip = request.args['ip'][0]
        tracker = self.parent.director.getTracker(
            serviceName=service, groupName=group)
        tracker.newHost(name=name, ip=ip)
        # also add to conf DOM object
        msg = 'Host %s(%s) added to %s / %s' % (name, ip, group, service)
        request.redirect('/running?resultMessage=%s' % urllib.quote(msg))
        return "OK"


class AdminServer(resource.Resource):
    """
    The admin server page is the root web object that publishes all the other
    resources.
    """
    def __init__(self, conf, director):
        resource.Resource.__init__(self)
        self.conf = conf
        self.director = director
        self.starttime = time.time()
        self.serverVersion = "%s/%s" % (txlb.shortName, txlb.version)

    def unauthorized(self):
        return UnauthorizedResource()

    def authenticateUser(self, request):
        # XXX this needs to be replaced with a guard/cred
        authstr = request.getHeader('Authorization')
        if not authstr:
            return False
        type, auth = authstr.split()
        if type.lower() != 'basic':
            return False
        auth = auth.decode('base64')
        user, pw = auth.split(':',1)
        userObj = self.conf.admin.getUser(user)
        if (userObj and userObj.checkPW(pw)):
            return True
        return False


    def getChild(self, name, request):
        """
        A simple object publisher that mapes part of a URL path to an object.
        """
        if not self.authenticateUser(request):
            return self.unauthorized()
        if name == 'running' or name == '':
            # XXX it's probably going to be better to do these checks from
            # within the RunningPage itself, in order to avoide a large
            # duplication of page code
            if self.director.isReadOnly:
                page = RunningReadOnlyPage(self)
            else:
                page = RunningPage(self)
            return page
        elif name == 'txlb.css':
            return StyleSheet()
        elif name == 'running.xml':
            return RunningConfig(self)
        elif name == 'config.xml':
            return StoredConfig(self)
        elif name == 'delHost':
            return DeleteHost(self)
        elif name == 'addHost':
            return AddHost(self)
        return resource.Resource.getChild(self, name, request)


