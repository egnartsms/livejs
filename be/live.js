(function () {
   'use strict';

   let $ = {
      livejs: {
         projectId: 'a559f0f3ff8744bb944f1dda48650b4f',
         moduleId: 'acc0b54988854dd9b5e74d269ea731e1',
         nontrackedKeys: [
            "port",
            "socket",
            "projects",
            "modules",
            "orderedKeysMap",
            "inspectionSpaces"
         ],
      },

      port: null,

      socket: null,

      bootload: function ({otherModules, projectPath, port}) {
         function byId(things) {
            let res = {};
            for (let thing of things) {
               res[thing.id] = thing;
            }
            return res;
         }

         // This is just to be able to access things in Chrome console
         window.live = $;

         // Initialize .projects and .modules structures
         let modules = [{
            id: $.livejs.moduleId,
            projectId: $.livejs.projectId,
            name: 'live.js',
            value: $
         }];

         for (let {name, src} of otherModules) {
            let value = window.eval(src);
            
            value['init'].call(null);

            modules.push({
               id: value['livejs']['moduleId'],
               projectId: $.livejs.projectId,
               name: name,
               value: value
            })
         }

         $.projects = {
            [$.livejs.projectId]: {
               id: $.livejs.projectId,
               name: 'Live.JS',
               path: projectPath,
               modules: byId(modules)
            }
         };
         $.modules = byId(modules);

         $.port = port;
         $.orderedKeysMap = new WeakMap;
         $.inspectionSpaces = {};
      
         $.resetSocket();
      },

      onSocketOpen: function () {
         console.log("Connected to LiveJS FE");
      },

      onSocketClose: function (evt) {
         $.resetSocket();
      },

      resetSocket: function () {
         $.socket = new WebSocket(`ws://localhost:${$.port}/ws`);
         $.socket.onmessage = $.onSocketMessage;
         $.socket.onopen = $.onSocketOpen;
         $.socket.onclose = $.onSocketClose;
      },

      onSocketMessage: function (evt) {
         let request = JSON.parse(evt.data);
      
         try {
            $.requestHandlers[request['type']].call(null, request['args']);
         }
         catch (e) {
            $.respondFailure('generic', {
               message: e.stack
            });
         }
      },

      send: function (message) {
         $.socket.send(JSON.stringify(message));
      },

      respondFailure: function (error, info) {
         $.send({
            type: 'response',
            success: false,
            error: error,
            info: info
         });
      },

      respondSuccess: function (value=null) {
         $.send({
            type: 'response',
            success: true,
            value: value
         });
      },

      persist: function (requests) {
         if (!(requests instanceof Array)) {
            requests = [requests];
         }
         $.send({
            type: 'persist',
            requests: requests
         });
      },

      evalFBody: function ($obj, code) {
         let func = new Function('$', "'use strict';\n" + code);
         return func.call(null, $obj);
      },

      evalExpr: function ($obj, code) {
         return $.evalFBody($obj, `return (${code});`);
      },

      hasOwnProperty: function (obj, prop) {
         return Object.prototype.hasOwnProperty.call(obj, prop);
      },

      orderedKeysMap: "new Object()",

      ensureOrdkeys: function (obj) {
         let ordkeys = $.orderedKeysMap.get(obj);
         if (ordkeys === undefined) {
            ordkeys = Object.keys(obj);
            $.orderedKeysMap.set(obj, ordkeys);
         }
         return ordkeys;
      },

      keys: function (obj) {
         return $.orderedKeysMap.get(obj) || Object.keys(obj);
      },

      entries: function* (obj) {
         for (let key of $.keys(obj)) {
            yield [key, obj[key]];
         }
      },

      deleteProp: function (obj, prop) {
         let ordkeys = $.orderedKeysMap.get(obj);
         if (ordkeys) {
            let index = ordkeys.indexOf(prop);
            if (index === -1) {
               return;
            }
            ordkeys.splice(index, 1);
         }
      
         delete obj[prop];
      },

      setProp: function (obj, key, value) {
         let ordkeys = $.orderedKeysMap.get(obj);
         if (ordkeys && !ordkeys.includes(key)) {
            ordkeys.push(key);
         }
         obj[key] = value;
      },

      insertProp: function (obj, key, value, pos) {
         let ordkeys = $.ensureOrdkeys(obj);
         let existingIdx = ordkeys.indexOf(key);
      
         ordkeys.splice(pos, 0, key);
         obj[key] = value;
      
         if (existingIdx !== -1) {
            if (existingIdx >= pos) {
               existingIdx += 1;
            }
            ordkeys.splice(existingIdx, 1);
         }
      },

      serialize: function serialize(obj) {
         switch (typeof obj) {
            case 'function':
            return {
               type: 'function',
               value: obj.toString()
            };
      
            case 'string':
            return {
               type: 'leaf',
               value: JSON.stringify(obj)
            };
      
            case 'number':
            case 'boolean':
            case 'undefined':
            return {
               type: 'leaf',
               value: String(obj)
            };
         }
      
         if (obj === null) {
            return {
               type: 'leaf',
               value: 'null'
            };
         }
      
         if (obj instanceof RegExp) {
            return {
               type: 'leaf',
               value: obj.toString()
            };
         }
      
         if (obj instanceof Array) {
            return {
               type: 'array',
               value: Array.from(obj, serialize)
            };
         }
      
         if (Object.getPrototypeOf(obj) !== Object.prototype) {
            console.log(obj);
            throw new Error(`Cannot serialize objects with non-standard prototype`);
         }
      
         return {
            type: 'object',
            value: Object.fromEntries(
               Array.from($.entries(obj), ([k, v]) => [k, serialize(v)])
            )
         };
      },

      nthValue: function (obj, n) {
         if (obj instanceof Array) {
            return obj[n];
         }
         else {
            return obj[$.keys(obj)[n]];
         }
      },

      valueAt: function (root, path) {
         let value = root;

         for (let n of path) {
            value = $.nthValue(value, n);
         }

         return value;
      },

      parentKeyAt: function (root, path) {
         if (path.length === 0) {
            throw new Error(`Path cannot be empty`);
         }
      
         let 
            parentPath = path.slice(0, -1),
            lastPos = path[path.length - 1],
            parent = $.valueAt(root, parentPath);
      
         if (parent instanceof Array) {
            return {parent, key: lastPos};
         }
         else {
            return {parent, key: $.keys(parent)[lastPos]};
         }
      },

      keyAt: function (root, path) {
         let {parent, key} = $.parentKeyAt(root, path);
         $.checkObject(parent);
         return key;
      },

      checkObject: function (obj) {
         if (Object.getPrototypeOf(obj) !== Object.prototype) {
            throw new Error(`Object/array mismatch: expected object, got ${obj}`);
         }
      },

      checkArray: function (obj) {
         if (!(obj instanceof Array)) {
            throw new Error(`Object/array mismatch: expected array, got ${obj}`)
         }
      },

      moveArrayItem: function (array, pos, fwd) {
         let
            value = array[pos],
            newPos = $.moveNewPos(array.length, pos, fwd);
      
         array.splice(pos, 1);
         array.splice(newPos, 0, value);
      
         return newPos;
      },

      moveNewPos: function (len, i, fwd) {
         return fwd ? (i === len - 1 ? 0 : i + 1) : 
                      (i === 0 ? len - 1 : i - 1);
      },

      projects: null,

      moduleObject: function (mid) {
         return $.modules[mid].value;
      },

      inspectionSpaces: null,

      inspectionSpace: function (spaceId) {
         if (!(spaceId in $.inspectionSpaces)) {
            $.inspectionSpaces[spaceId] = {
               obj2id: new Map,
               id2obj: new Map,
               nextId: 1
            };
         }
      
         return $.inspectionSpaces[spaceId];
      },

      inspecteeId: function (space, object) {
         if (!((typeof object === 'object' && object !== null) || 
               (typeof object === 'function'))) {
            throw new Error(`Invalid inspected object: ${object}`);
         }
      
         if (space.obj2id.has(object)) {
            return space.obj2id.get(object);
         }
      
         let id = space.nextId++;
         space.obj2id.set(object, id);
         space.id2obj.set(id, object);
      
         return id;
      },

      inspect: function (space, obj, deeply) {
         switch (typeof obj) {
            case 'bigint':
               throw new Error(`Serialization of bigints is not implemented`);
      
            case 'symbol':
               throw new Error(`Serialization of symbols is not implemented`);
      
            case 'string':
            return {
               type: 'leaf',
               value: JSON.stringify(obj)
            };
      
            case 'number':
            case 'boolean':
            case 'undefined':
            return {
               type: 'leaf',
               value: String(obj)
            };
      
            case 'function':
            return $.inspectFunc(space, obj);
         }
      
         if (obj === null) {
            return {
               type: 'leaf',
               value: 'null'
            };
         }
      
         if (obj instanceof RegExp) {
            return {
               type: 'leaf',
               value: obj.toString()
            };
         }
      
         if (deeply) {
            return $.inspectObjectDeeply(space, obj);
         }
         else {
            return $.inspectObjectShallowly(space, obj);
         }
      },

      inspectFunc: function (space, func) {
         return {
            type: 'function',
            id: $.inspecteeId(space, func),
            value: func.toString()
         };
      },

      inspectObjectShallowly: function (space, object) {
         if (object instanceof Array) {
            return {
               type: 'array',
               id: $.inspecteeId(space, object)
            };
         }
         else {
            return {
               type: 'object',
               id: $.inspecteeId(space, object)
            };
         }
      },

      inspectObjectDeeply: function (space, object) {
         if (object instanceof Array) {
            return {
               type: 'array',
               id: $.inspecteeId(space, object),
               value: Array.from(object, x => $.inspect(space, x, false))
            };
         }
      
         if (typeof object === 'function') {
            return $.inspectFunc(space, object);
         }
      
         let result = {
            __proto: $.inspect(space, Object.getPrototypeOf(object), false)
         };
         let nonvalues = {};
      
         for (let [prop, desc] of Object.entries(Object.getOwnPropertyDescriptors(object))) {
            if ($.hasOwnProperty(desc, 'value')) {
               result[prop] = $.inspect(space, desc.value, false);
            }
            else {
               result[prop] = {
                  type: 'unrevealed',
                  parentId: $.inspecteeId(space, object),
                  prop: prop
               };
               nonvalues[prop] = desc;
            }
         }
      
         for (let [prop, desc] of Object.entries(nonvalues)) {
            if (desc.get) {
               result['get ' + prop] = $.inspectFunc(space, desc.get);
            }
            if (desc.set) {
               result['set ' + prop] = $.inspectFunc(space, desc.set);
            }
         }
      
         return {
            type: 'object',
            id: $.inspecteeId(space, object),
            value: result
         };
      },

      isKeyNontracked: function (module, key) {
         return module.livejs.nontrackedKeys.includes(key);
      },

      requestHandlers: {
         getKeyAt: function ({mid, path}) {
            $.respondSuccess($.keyAt($.moduleObject(mid), path));
         },
         getValueAt: function ({mid, path}) {
            $.respondSuccess(
               $.serialize($.valueAt($.moduleObject(mid), path))
            );
         },
         sendAllEntries: function ({mid}) {
            let result = [];
            let module = $.moduleObject(mid);
         
            for (let [key, value] of $.entries(module)) {
               if ($.isKeyNontracked(module, key)) {
                  result.push([key, $.serialize('new Object()')])
               }
               else {
                  result.push([key, $.serialize(value)]);   
               }
            }
         
            $.respondSuccess(result);
         },
         replace: function ({mid, path, codeNewValue}) {
            let 
               {parent, key} = $.parentKeyAt($.moduleObject(mid), path),
               newValue = $.evalExpr($.moduleObject(mid), codeNewValue);
         
            parent[key] = newValue;
         
            $.persist({
               type: 'replace',
               mid,
               path,
               newValue: $.serialize(newValue)
            });
            $.respondSuccess();
         },
         renameKey: function ({mid, path, newName}) {
            let {parent, key} = $.parentKeyAt($.moduleObject(mid), path);
         
            $.checkObject(parent);
         
            if ($.hasOwnProperty(parent, newName)) {
               $.respondFailure('duplicate_key', {
                  objPath: path,
                  duplicatedKey: newName,
                  message: `Cannot rename to ${newName}: duplicate property name`
               });
               return;
            }
         
            let ordkeys = $.ensureOrdkeys(parent);
            ordkeys[ordkeys.indexOf(key)] = newName;
            parent[newName] = parent[key];
            delete parent[key];
         
            $.persist({
               type: 'rename_key',
               mid,
               path,
               newName
            });
            $.respondSuccess();
         },
         addArrayEntry: function ({mid, parentPath, pos, codeValue}) {
            let parent = $.valueAt($.moduleObject(mid), parentPath);
            let value = $.evalExpr($.moduleObject(mid), codeValue);
         
            $.checkArray(parent);
         
            parent.splice(pos, 0, value);
         
            $.persist({
               type: 'insert',
               mid,
               path: parentPath.concat(pos),
               key: null,
               value: $.serialize(value)
            });
            $.respondSuccess();
         },
         addObjectEntry: function ({mid, parentPath, pos, key, codeValue}) {
            let parent = $.valueAt($.moduleObject(mid), parentPath);
            let value = $.evalExpr($.moduleObject(mid), codeValue);
         
            $.checkObject(parent);
            if ($.hasOwnProperty(parent, key)) {
               throw new Error(`Cannot insert property ${key}: it already exists`);
            }
         
            $.insertProp(parent, key, value, pos);   
         
            $.persist({
               type: 'insert',
               mid,
               path: parentPath.concat(pos),
               key: key,
               value: $.serialize(value)
            });
            $.respondSuccess();
         },
         move: function ({mid, path, fwd}) {
            let {parent, key} = $.parentKeyAt($.moduleObject(mid), path);
            let value = parent[key];
            let newPos;
         
            if (parent instanceof Array) {
               newPos = $.moveArrayItem(parent, key, fwd);
            }
            else {
               let props = $.ensureOrdkeys(parent);
               newPos = $.moveArrayItem(props, props.indexOf(key), fwd);
            }
         
            let newPath = path.slice(0, -1);
            newPath.push(newPos);
         
            $.persist([
               {
                  type: 'delete',
                  mid,
                  path: path
               }, 
               {
                  type: 'insert',
                  mid,
                  path: newPath,
                  key: parent instanceof Array ? null : key,
                  value: $.isKeyNontracked($.moduleObject(mid), key) ?
                     $.serialize('new Object()') : $.serialize(value)
               }
            ]);
            $.respondSuccess(newPath);
         },
         deleteEntry: function ({mid, path}) {
            let {parent, key} = $.parentKeyAt($.moduleObject(mid), path);
         
            if (parent instanceof Array) {
               parent.splice(path[path.length - 1], 1);
            }
            else {
               $.deleteProp(parent, key);
            }
         
            $.persist({
               type: 'delete',
               mid,
               path: path
            });
            $.respondSuccess();
         },
         sendModules: function () {
            $.respondSuccess(
               Object.values($.modules).map(m => ({
                  id: m.id,
                  name: m.name,
                  path: m.path
               }))
            );
         },
         loadModules: function ({modules}) {
            // modules: [{id, name, path, source}]
            //
            // We keep module names unique.
            function isModuleOk({name, id}) {
               return (
                  !$.hasOwnProperty($.modules, id) &&
                  Object.values($.modules).every(({xname}) => xname !== name)
               );
            }
         
            if (!modules.every(isModuleOk)) {
               throw new Error(`Cannot add modules: duplicates found`);
            }
         
            let values = modules.map(({source}) => $.evalExpr(null, source));
         
            for (let i = 0; i < modules.length; i += 1) {
               let m = modules[i], value = values[i];
         
               if (value['init']) {
                  value['init'].call(null);
               }
         
               $.modules[m['id']] = {
                  id: m['id'],
                  name: m['name'],
                  path: m['path'],
                  value: value
               };
            }
         
            $.respondSuccess();
         },
         replEval: function ({mid, spaceId, code}) {
            let obj = $.evalExpr($.moduleObject(mid), code);
            $.respondSuccess($.inspect($.inspectionSpace(spaceId), obj, true));
         },
         inspectObjectById: function ({spaceId, id}) {
            let space = $.inspectionSpace(spaceId);
            let object = space.id2obj.get(id);
            if (!object) {
               throw new Error(`Unknown object id: ${id}`);
            }
         
            $.respondSuccess($.inspectObjectDeeply(space, object));
         },
         inspectGetterValue: function ({spaceId, parentId, prop}) {
            let space = $.inspectionSpace(spaceId);
            let parent = space.id2obj.get(parentId);
            if (!parent) {
               throw new Error(`Unknown object id: ${parentId}`);
            }
         
            let result;
            try {
               result = parent[prop];
            }
            catch (e) {
               $.respondFailure('getter_threw', {
                  excClassName: e.constructor.name,
                  excMessage: e.message,
                  message: `Getter threw an exception`
               });
               return;
            }
         
            $.respondSuccess($.inspect(space, result, true));
         },
         deleteInspectionSpace: function ({spaceId}) {
            let space = $.inspectionSpaces[spaceId];
            if (!space) {
               $.respondSuccess(false);
               return;
            }
         
            space.id2obj.clear();
            space.obj2id.clear();
            delete $.inspectionSpaces[spaceId];
         
            $.respondSuccess(true);
         }
      }
   };

   return $;
})();
