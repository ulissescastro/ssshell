#!/usr/bin/env python
import paramiko, sys, socket, time

try:
    # create client object
    client = paramiko.SSHClient()
    # auto add keys
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # global host_keys
    host_keys = client.get_host_keys()
    # create connection
    client.connect(
            hostname = '127.0.0.1', 
            port = 4444, 
            username = 'root', 
            password = 'x', 
            allow_agent = False, 
            look_for_keys = False, 
            gss_deleg_creds = False
            )
    # lets get the party started
    transport = client.get_transport()
    # is authenticated? 
    if transport.is_authenticated():
        ip, port = transport.getpeername()
        session_channel = transport.open_session()
        session_channel.get_pty()
        session_channel.set_combine_stderr(True)
        session_channel.exec_command('ps auxww')
        while True:
            if session_channel.exit_status_ready():
                print session_channel.recv(-1)
                transport.close()
                break
            else:
                time.sleep(0.1)
            # no? auth fail, close transport and move on...
    else:
        transport.close()
except paramiko.AuthenticationException, e:
    print "paramiko.AuthenticationException: %s" % e
except paramiko.SSHException, e:
    print "SSHException: %s" % e
except socket.error, e:
    print "socket.error: %s" % e

