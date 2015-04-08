#!/usr/bin/env python
# Licensed under latest GNU GPL: http://www.gnu.org/licenses/gpl.html
# Ulisses Castro <uss.thebug@gmail.com>

# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import time
import socket
import random
import string
import paramiko
import itertools

from multiprocessing import Pool
from collections import OrderedDict

try:
    from scp import SCPClient
    scp_module = True
except Exception:
    scp_module = False
    pass


def randomword(length):
   return ''.join(random.choice(string.lowercase) for i in range(length))


def ssh_client(client, host):
    ubnt_id_rsa = '/home/ucastro/Devel/sshelf/airos-mass/pyubnt/housekeeping/id_rsa'
    try:
        client.connect(host, 22, 'user', 'password', key_filename=ubnt_id_rsa, allow_agent=False, look_for_keys=False, gss_deleg_creds=False, timeout=30)
        return client
    except paramiko.AuthenticationException, e:
        #print "AuthenticationException: %s" % e
        pass
    except paramiko.SSHException, e:
        #print "SSHException: %s" % e
        pass
    except socket.error, e:
        #print "socket.error: %s" % e
        pass

    return


def open_sft_scp_client(client):
    # try via sftp...
    try:
        sftp = client.open_sftp()
        return sftp
    except Exception, e:
        print "open_sft_scp_client sftp: %s" % e
        pass

    # otherwise, scp instead...
    try:
        if scp_module and not sftp:
            scp = SCPClient(client.get_transport())
            return scp
    except Exception, e:
        print "open_sft_scp_client scp: %s" % e
        pass

    return


def execute(client, command, timeout=10, sudo=False):
    output = ""

    if sudo:
        command = "/usr/bin/sudo su -c '%s'" % command

    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=True)
        # append stderr to stdout
        output = stdout.read() + stderr.read()
        # close files
        [std.close() for std in (stdin, stdout, stderr)]
    except Exception, e:
        print "execute: %s" % e
        pass

    return output


def download(client, src, dst):
    try:
        download_cli = open_sft_scp_client(client)
        if download_cli:
            download_cli.get(src, dst)
            return True
    except Exception, e:
        print "download: %s" % e
        pass

    return False


def upload(client, src, dst):
    try:
        upload_cli = open_sft_scp_client(client)
        if upload_cli:
            upload_cli.put(src, dst)
            return True
    except Exception, e:
        print "upload: %s" % e
        pass

    return False


def upload_and_execute(client, src, sudo=False):
    # src sript filename
    src = 'scripts/%s' % src
    dst = '/tmp/%s' % randomword(10)
    
    # upload
    if upload(client, src, dst):
        # prepare commands
        exec_script = '/bin/bash %s' % remote_path
        rm_script = '/bin/rm -fv %s' % remote_path
        # execute
        if sudo:
            script_output = execute(client, exec_script, sudo)
        else:
            script_output = execute(client, exec_script)
        # return True if output is empty
        if script_output and len(script_output) > 0:
            return script_output
        else:
            return True

        # clean up
        cleanup = execute(client, rm_script)
        if not cleanup:
            print "clean up problem, check."

    return False


def load_module(module_name):
    module = 'modules/%s.json' % module_name
    try:
        with open(module) as module_settings:
            # settings = json.load(module_settings, object_hook=object_hook_module_handler)
            settings = json.load(module_settings, object_pairs_hook=OrderedDict)
            return settings
    except Exception, e:
        print "load_module: %s" % e
        pass

    return


def worker(ip_action_args_tuple):
    output = ""
    connected = False
    ip, client, action, args = ip_action_args_tuple
    try:
        client = ssh_client(client, ip)
        if client:
            connected = True
            # don't run actions twice
            if not host_keys.lookup(ip):
                output = globals()[action](client, *args)
                client.close()
                log_handler(ip, output)
            else:
                print "%s host already used" % ip
    except Exception, e:
        print "worker: %s" % e
        pass
    
    return (ip, connected, output)


def pool_args(ip_list, client, action, args):
    repeat_times = len(ip_list)
    ip_action_args_tuple = zip( ip_list, 
                                itertools.repeat(client, repeat_times), 
                                itertools.repeat(action, repeat_times), 
                                itertools.repeat(args, repeat_times)
                                )

    return ip_action_args_tuple


def start_process(client):
    global host_keys
    host_keys = client.get_host_keys()
    return


def safe_write_output(log_file, output):
    if not os.path.exists(log_file):
        with open(log_file, 'wb') as log:
            log.write(output)
    else:
        with open(log_file, 'a') as log:
            log.write(output)

    return


def log_handler(ip, output):
    # essa funcao sera substituida pelo logger para o arcsight
    if output:
        #date = time.strftime("%d%m%y-%H%M%S")
        #date = time.strftime("%d%m%y")
        log_dir = 'logs/%s' % ip
        if not os.path.isdir(log_dir):
            os.mkdir(log_dir)
        
        log_success = "logs/sucess.log"
        log_name = "%s.log" % randomword(10)
        log_file = '%s/%s' % (log_dir, log_name)
        safe_write_output(log_file, output)
        ip = "%s\n" % ip
        safe_write_output(log_success, ip)

    return


def main(ip_list, module_name):
    results = []
    allowed_actions = ['execute', 'download', 'upload', 'upload_and_execute']
    
    # load task settings
    settings = load_module(module_name)

    # randomize ips
    random.shuffle(ip_list)

    # info
    print "info: %s" % settings['info']
    print "threads: %s" % settings['threads']

    # create single client for multiple tasks
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # set how many threads
    pool = Pool(settings['threads'], initializer=start_process(client))

    # action iter
    for action, action_args in settings['action'].iteritems():
        if action in allowed_actions:
            results = pool.map(worker, pool_args(ip_list, client, action, list(action_args.values())))
            pool.close()
            pool.join()

    return results


if __name__ == '__main__':
    # tests.... tests...
    servers = open(sys.argv[1], 'r').read().split('\n')[:-1]
    results = main(servers, 'single_command')
    count = 0
    for result in results:
        ip, connected, output = result
        if connected:
            print "%s\n%s" % (ip, output)
            count += 1

    print "done [%s/%s]" % (count, len(servers))
