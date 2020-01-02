window.live = (function () {
   'use strict';

   let $ = {
      nontrackedKeys: [
         "socket",
         "orderedKeysMap",
         "modules"
      ],

      socket: null,

      init: function () {
         $.modules = Object.create(null);
         $.modules[1] = {
            id: 1,
            name: 'live',
            path: null,
            value: $
         };
         $.orderedKeysMap = new WeakMap;
      
         $.resetSocket();
      },

      onSocketOpen: function () {
         console.log("Connected to LiveJS FE");
      },

      onSocketClose: function (evt) {
         $.resetSocket();
      },

      resetSocket: function () {
         $.socket = new WebSocket('ws://localhost:8001/wsconnect');
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
            $.respondFailure(`LiveJS request failed:\n${e.stack}`);
         }
      },

      requestHandlers: {
         getKeyAt: function ({mid, path}) {
            $.respondSuccess($.keyAt($.moduleRoot(mid), path));
         },
         getValueAt: function ({mid, path}) {
            $.respondSuccess(
               $.prepareForSerialization($.valueAt($.moduleRoot(mid), path))
            );
         },
         sendAllEntries: function ({mid}) {
            let result = [];
            let module =  $.moduleRoot(mid);
         
            for (let [key, value] of $.entries(module)) {
               if (module.nontrackedKeys && module.nontrackedKeys.includes(key)) {
                  result.push([key, $.prepareForSerialization('new Object()')])
               }
               else {
                  result.push([key, $.prepareForSerialization(value)]);   
               }
            }
         
            $.respondSuccess(result);
         },
         replace: function ({mid, path, codeNewValue}) {
            let 
               {parent, key} = $.parentKeyAt($.modulesRoot(mid), path),
               newValue = $.evalExpr(codeNewValue);
         
            parent[key] = newValue;
         
            $.persist({
               type: 'replace',
               mid,
               path,
               newValue: $.prepareForSerialization(newValue)
            });
            $.respondSuccess();
         },
         renameKey: function ({mid, path, newName}) {
            let {parent, key} = $.parentKeyAt($.moduleRoot(mid), path);
         
            $.checkObject(parent);
         
            if ($.hasOwnProperty(parent, newName)) {
               $.respondFailure(`Cannot rename to ${newName}: duplicate property name`);
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
            let parent = $.valueAt($.moduleRoot(mid), parentPath);
            let value = $.evalExpr(codeValue);
         
            $.checkArray(parent);
         
            parent.splice(pos, 0, value);
         
            $.persist({
               type: 'insert',
               mid,
               path: parentPath.concat(pos),
               key: null,
               value: $.prepareForSerialization(value)
            });
            $.respondSuccess();
         },
         addObjectEntry: function ({mid, parentPath, pos, key, codeValue}) {
            let parent = $.valueAt($.moduleRoot(mid), parentPath);
            let value = $.evalExpr(codeValue);
         
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
               value: $.prepareForSerialization(value)
            });
            $.respondSuccess();
         },
         move: function ({mid, path, fwd}) {
            let {parent, key} = $.parentKeyAt($.moduleRoot(mid), path);
            let value = parent[key];
            let newPos;
         
            if (Array.isArray(parent)) {
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
                  key: Array.isArray(parent) ? null : key,
                  value: $.prepareForSerialization(value)
               }
            ]);
            $.respondSuccess(newPath);
         },
         deleteEntry: function ({mid, path}) {
            let {parent, key} = $.parentKeyAt($.moduleRoot(mid), path);
         
            if (Array.isArray(parent)) {
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
         
            let values = modules.map(({source}) => $.evalExpr(source));
         
            for (let i = 0; i < modules.length; i += 1) {
               let m = modules[i], value = values[i];
         
               $.modules[m['id']] = {
                  id: m['id'],
                  name: m['name'],
                  path: m['path'],
                  value: value
               };
            }
         
            $.respondSuccess();
         }
      },

      send: function (message) {
         $.socket.send(JSON.stringify(message));
      },

      respondFailure: function (message) {
         $.send({
            type: 'response',
            success: false,
            message: message
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
         if (!Array.isArray(requests)) {
            requests = [requests];
         }
         $.send({
            type: 'persist',
            requests: requests
         });
      },

      evalFBody: function (code) {
         let func = new Function('$', "'use strict';\n" + code);
         return func.call(null, $);
      },

      evalExpr: function (code) {
         return $.evalFBody(`return (${code});`);
      },

      hasOwnProperty: function (obj, prop) {
         return Object.prototype.hasOwnProperty.call(obj, prop);
      },

      orderedKeysMap: null,

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

      prepareForSerialization: function prepare(obj) {
         switch (typeof obj) {
            case 'function':
            return {
               __leaf_type__: 'function',
               value: obj.toString()
            };

            case 'string':
            return {
               __leaf_type__: 'js-value',
               value: JSON.stringify(obj)
            };

            case 'number':
            case 'boolean':
            case 'undefined':
            return {
               __leaf_type__: 'js-value',
               value: String(obj)
            };
         }

         if (obj === null) {
            return {
               __leaf_type__: 'js-value',
               value: 'null'
            };
         }

         if (Array.isArray(obj)) {
            return Array.from(obj, prepare);
         }

         let proto = Object.getPrototypeOf(obj);

         if (proto === RegExp.prototype) {
            return {
               __leaf_type__: 'js-value',
               value: obj.toString()
            };
         }

         if (proto !== Object.prototype) {
            throw new Error(`Cannot serialize objects with non-standard prototype`);
         }

         return Object.fromEntries($.keys(obj).map(k => [k, prepare(obj[k])]));
      },

      nthValue: function (obj, n) {
         if (Array.isArray(obj)) {
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

         if (Array.isArray(parent)) {
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
         if (!Array.isArray(obj)) {
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

      modules: null,

      moduleRoot: function (mid) {
         return $.modules[mid].value;
      }
   };

   $.init();

   return $;
})();
