window.live = (function () {
   'use strict';

   let $ = {
      nontrackedKeys: [
         "socket",
         "orderedKeysMap",
         "modules",
         "eval"
      ],

      socket: null,

      init: function () {
         $.modules = Object.create(null);
         $.modules['live'] = {
            name: 'live',
            path: null,
            value: $
         };
         $.eval = window.eval;
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

      onSocketMessage: function (e) {
         let func;

         try {
            func = new Function('$', "'use strict';\n" + e.data);
         }
         catch (e) {
            $.sendFailure(`Failed to compile JS code:\n ${e}`);
            return;
         }

         try { 
            func.call(null, $);
         }
         catch (e) {
            $.sendFailure(`Unhandled exception:\n ${e.stack}`);
            return;
         }
      },

      send: function (msg) {
         $.socket.send(JSON.stringify(msg));
      },

      sendFailure: function (message) {
         $.send({
            success: false,
            message: message
         });
      },

      sendSuccess: function (response, actions=null) {
         $.send({
            success: true,
            response: response,
            actions: actions || []
         });
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

      valueAt: function (path) {
         let value = $;

         for (let n of path) {
            value = $.nthValue(value, n);
         }

         return value;
      },

      parentKeyAt: function (path) {
         if (path.length === 0) {
            throw new Error(`Path cannot be empty`);
         }

         let 
            parentPath = path.slice(0, -1),
            lastPos = path[path.length - 1],
            parent = $.valueAt(parentPath);

         if (Array.isArray(parent)) {
            return {parent, key: lastPos};
         }
         else {
            return {parent, key: $.keys(parent)[lastPos]};
         }
      },

      keyAt: function (path) {
         let {parent, key} = $.parentKeyAt(path);
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

      sendAllEntries: function () {
         let result = [];
         for (let [key, value] of $.entries($)) {
            if ($.nontrackedKeys.includes(key)) {
               result.push([key, $.prepareForSerialization('new Object()')])
            }
            else {
               result.push([key, $.prepareForSerialization(value)]);   
            }
         }

         $.sendSuccess(result);
      },

      sendValueAt: function (path) {
         $.sendSuccess($.prepareForSerialization($.valueAt(path)));
      },

      sendKeyAt: function (path) {
         $.sendSuccess($.keyAt(path));
      },

      replace: function (path, newValueClosure) {
         let 
            {parent, key} = $.parentKeyAt(path),
            newValue = newValueClosure.call(null);

         parent[key] = newValue;

         $.sendSuccess(null, [{
            type: 'replace',
            path: path,
            newValue: $.prepareForSerialization(newValue)
         }]);
      },

      renameKey: function (path, newName) {
         let {parent, key} = $.parentKeyAt(path);

         $.checkObject(parent);
         if ($.hasOwnProperty(parent, newName)) {
            $.sendFailure(`Cannot rename to ${newName}: duplicate property name`);
            return;
         }

         let ordkeys = $.ensureOrdkeys(parent);
         ordkeys[ordkeys.indexOf(key)] = newName;
         parent[newName] = parent[key];
         delete parent[key];

         $.sendSuccess(null, [{
            type: 'rename_key',
            path,
            newName
         }])
      },

      move: function (path, fwd) {
         let {parent, key} = $.parentKeyAt(path);
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
      
         $.sendSuccess(newPath, [{
            type: 'delete',
            path: path
         }, {
            type: 'insert',
            path: newPath,
            key: Array.isArray(parent) ? null : key,
            value: $.prepareForSerialization(value)
         }]);   
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

      deleteEntry: function (path) {
         let {parent, key} = $.parentKeyAt(path);

         if (Array.isArray(parent)) {
            parent.splice(path[path.length - 1], 1);
         }
         else {
            $.deleteProp(parent, key);
         }

         $.sendSuccess(null, [{
            type: 'delete',
            path: path
         }]);
      },

      addArrayEntry: function (parentPath, pos, valueClosure) {
         let parent = $.valueAt(parentPath);
         let value = valueClosure.call(null);
      
         $.checkArray(parent);
      
         parent.splice(pos, 0, value);
      
         $.sendSuccess(null, [{
            type: 'insert',
            path: parentPath.concat(pos),
            key: null,
            value: $.prepareForSerialization(value)
         }]);
      },

      addObjectEntry: function (parentPath, pos, key, valueClosure) {
         let value = valueClosure.call(null);
         let parent = $.valueAt(parentPath);
      
         $.checkObject(parent);
         if ($.hasOwnProperty(parent, key)) {
            throw new Error(`Cannot insert property ${key}: it already exists`);
         }
      
         $.insertProp(parent, key, value, pos);   
      
         $.sendSuccess(null, [{
            type: 'insert',
            path: parentPath.concat(pos),
            key: key,
            value: $.prepareForSerialization(value)
         }]);
      },

      eval: null,

      modules: null,

      sendModules: function () {
         $.sendSuccess(
            Object.values($.modules).map(m => ({name: m.name, path: m.path}))
         );
      },

      loadModules: function (modules) {
         // modules: [{name, path, source}]
         if (modules.some(({name}) => $.hasOwnProperty($.modules, name))) {
            throw new Error(`Cannot add modules: duplicate name(s)`);
         }
      
         let values = modules.map(({source}) => $.eval(source));
      
         for (let i = 0; i < modules.length; i += 1) {
            $.modules[modules[i]['name']] = {
               name: modules[i]['name'],
               path: modules[i]['path'],
               value: values[i]
            };
         }
      
         $.sendSuccess(null);
      }
   };

   $.init();

   return $;
})();
