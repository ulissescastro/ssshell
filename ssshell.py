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


def ssh_client(client, hostname,
               username, password, port, key_filename, timeout=30):
    try:
        # create client object
        client = paramiko.SSHClient()
        # auto add keys
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # global host_keys
        host_keys = client.get_host_keys()
        # create connection
        client.connect(hostname=hostname, port=port,
                       username=username, password=password,
                       timeout=timeout, allow_agent=False,
                       look_for_keys=False, gss_deleg_creds=False)
        # lets get this party started
        transport = client.get_transport()
        return transport
    except paramiko.AuthenticationException, e:
        # print "AuthenticationException: %s" % e
        pass
    except paramiko.SSHException, e:
        # print "SSHException: %s" % e
        pass
    except socket.error, e:
        # print "socket.error: %s" % e
        pass

    return


def open_sft_scp_client(transport):
    # try via sftp...
    try:
        sftp = transport.open_sftp()
        return sftp
    except Exception, e:
        print "open_sft_scp_client sftp: %s" % e
        pass

    # otherwise, scp instead...
    try:
        if scp_module and not sftp:
            scp = SCPClient(transport)
            return scp
    except Exception, e:
        print "open_sft_scp_client scp: %s" % e
        pass

    return


def download(transport, src, dst):
    try:
        download_cli = open_sft_scp_client(transport)
        if download_cli:
            download_cli.get(src, dst)
            # close sftp channel (transport still open)
            download_cli.close()
            return True
    except Exception, e:
        print "download: %s" % e
        pass

    return False


def upload(transport, src, dst):
    try:
        upload_cli = open_sft_scp_client(transport)
        if upload_cli:
            upload_cli.put(src, dst)
            # close sftp channel (transport still open)
            upload_cli.close()
            return True
    except Exception, e:
        print "upload: %s" % e
        pass

    return False


def execute(transport, command, sudo=False):
    if sudo:
        command = "/usr/bin/sudo su -c '%s'" % command

    try:
        session_channel = transport.open_session()
        session_channel.get_pty()
        session_channel.set_combine_stderr(True)
        session_channel.exec_command(command)
        return session_channel
    except Exception, e:
        print "command: %s" % command
        print "execute: %s" % e
        pass

    return


def check_output(session_channel):
    # this function will close connection (transport)
    while not session_channel.exit_status_ready():
        time.sleep(0.1)

    exit_status = session_channel.exit_status
    output = session_channel.recv(-1)
    session_channel.transport.close()

    return output


def upload_and_execute(transport, src, sudo=False):
    # src sript filename
    script_name = '/tmp/sss_%s' % randomword(10)

    # upload
    if upload(transport, src, tmp_random_script):
        # execute and auto-remove
        # check sample in script/default.sh
        command = '/bin/sh %s' % (script_name, script_name)
        session_channel = execute(transport, command, sudo)
    else:
        print "%s upload to %s failed " % (src, tmp_random_script)

    return session_channel


def load_module(module_name):
    module = 'modules/%s.json' % module_name
    try:
        with open(module) as module_settings:
            settings = json.load(module_settings,
                                 object_pairs_hook=OrderedDict)
            return settings
    except Exception, e:
        print "load_module: %s" % e
        pass

    return


def worker(tuple_args):
    ip, client, action, args = tuple_args
    try:
        transport = ssh_get_transport(client, ip)
    except Exception, e:
        print "worker: %s" % e
        pass

    if client:
        connected = True
        # don't run actions twice
        if not host_keys.lookup(ip):
            output = globals()[action](client, *args)
            client.close()
            log_handler(ip, output)
        else:
            print "%s host already used" % ip

    return (ip, connected, output)


def pool_args(ip_list, client, action, args):
    repeat_times = len(ip_list)
    tuple_args = zip(ip_list, itertools.repeat(client, repeat_times),
                     itertools.repeat(action, repeat_times),
                     itertools.repeat(args, repeat_times))

    return tuple_args


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
        # date = time.strftime("%d%m%y-%H%M%S")
        # date = time.strftime("%d%m%y")
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
    print "module info: %s" % settings['info']
    print "num of workers: %s" % settings['threads']

    # create single client for multiple tasks
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # set how many threads
    pool = Pool(settings['threads'], initializer=start_process(client))

    # action iter
    for action, action_args in settings['action'].iteritems():
        if action in allowed_actions:
            results = pool.map(worker,
                               pool_args(ip_list, client,
                                         action, list(action_args.values())))
            pool.close()
            pool.join()

    return results

if __name__ == '__main__':
    # tests.... tests...
    # TODO: retornar numero total de servidores,
    # numero total de servidores acessados,
    # numero total de servidores com execucao com sucesso
    servers = open(sys.argv[1], 'r').read().split('\n')[:-1]
    results = main(servers, 'download')
    count = 0
    for result in results:
        ip, connected, output = result
        if connected:
            print "%s\n%s" % (ip, output)
            count += 1

    print "done [%s/%s]" % (count, len(servers))
