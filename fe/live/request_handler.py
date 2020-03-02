import http.client as httpcli
import json
import os
import re

from live.gstate import config
from live.gstate import ws_handler
from live.lowlvl.http import Response
from live.lowlvl.websocket import WebSocket
from live.util.misc import file_contents


def request_handler(req):
    if req.path == '/ws':
        if ws_handler.is_connected:
            yield from Response(req, httpcli.BAD_REQUEST)
        else:
            websocket = WebSocket(req, ws_handler)
            ws_handler.connect(websocket)
            try:
                yield from websocket
            finally:
                ws_handler.disconnect()

        return
    
    if req.path == '/':
        bootload_path = os.path.join(config.be_root, '_bootload_template.js')
        bootload_code = file_contents(bootload_path)

        def replacer(mo):
            thing = mo.group(1).lower()
            if thing == 'port':
                return str(config.port)
            elif thing == 'project_module_name':
                return json.dumps('project.live')
            elif thing == 'project_path':
                return json.dumps(config.be_root)
            else:
                assert False

        bootload_code = re.sub(r'LIVEJS_(\w+)', replacer, bootload_code)

        yield from Response(req, httpcli.OK).send_string(
            bootload_code, mimetype='application/javascript'
        )
        return

    mo = re.match(r'/bootload/([\w.]+.js)$', req.path)
    if mo is None:
        yield from Response(req, httpcli.BAD_REQUEST)
        return

    module_name = mo.group(1)
    module_path = os.path.join(config.be_root, module_name)

    if not os.path.exists(module_path):
        yield from Response(req, httpcli.NOT_FOUND)
        return

    yield from Response(req, httpcli.OK).send_file(module_path)
