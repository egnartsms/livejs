window.root = (function () {
   let $ = {
      nontrackedKeys: [
         'socket',
         'orderedKeysMap'
      ],

      socket: null,

      initOnLoad: function () {
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
            func = new Function('$', e.data);
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

      orderedKeysMap: new WeakMap,

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

      entries: function (obj) {
         return $.keys(obj).map(key => [key, obj[key]]);
      },

      deleteProp: function (obj, prop) {
         let ordkeys = $.orderedKeysMap.get(obj);
         if (ordkeys) {
            let index = ordkeys.indexOf(prop);
            if (index === -1) {
               return;
            }
            ordkeys.splice(index, 1);
            delete obj[prop];
         }
         else {
            delete obj[prop];
         }
      },

      insertProp: function (obj, key, value, pos) {
         let ordkeys = $.ensureOrdkeys(obj);
         ordkeys.splice(pos, 0, key);
         obj[key] = value;
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

         return Object.fromEntries(
            $.entries(obj).map(([k, v]) => [k, prepare(v)])
            );
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

      path2ParentnKey: function (path) {
         let parent, child = $;

         for (let i = 0; i < path.length; i += 1) {
            parent = child;
            [key, child] = $.nthEntry(parent, path[i]);
         }

         return {parent, key};
      },

      nthEntry: function (obj, n) {
         if (Array.isArray(obj)) {
            return [String(n), obj[n]];
         }
         else {
            return $.entries(obj)[n];
         }
      },

      sendAllEntries: function () {
         let result = [];
         for (let [key, value] of Object.entries($)) {
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
         let {parent, key} = $.path2ParentnKey(path);
         $.sendSuccess($.prepareForSerialization(parent[key]));
      },

      sendKeyAt: function (path) {
         let {parent, key} = $.path2ParentnKey(path);
         $.sendSuccess(key);
      },

      replace: function (path, newValueClosure) {
         let newValue;

         try {
            newValue = newValueClosure.call(null);
         }
         catch (e) {
            $.sendFailure(`Failed to evaluate a new value:\n ${e.stack}`)
            return;
         }

         let {parent, key} = $.path2ParentnKey(path);
         parent[key] = newValue;

         $.sendSuccess(null, [{
            type: 'replace',
            path: path,
            newValue: $.prepareForSerialization(newValue)
         }]);
      },

      renameKey: function (path, newName) {
         let {parent, key} = $.path2ParentnKey(path);
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
         function newNodePos(len, i, fwd) {
            return fwd ? (i === len - 1 ? 0 : i + 1) : 
                         (i === 0 ? len - 1 : i - 1);
         }

         let
            {parent, key} = $.path2ParentnKey(path),
            value = parent[key],
            pos = path[path.length - 1],
            array = Array.isArray(parent) ? parent : $.ensureOrdkeys(parent),
            newPos = newNodePos(array.length, pos, fwd);

         let tem = array[pos];
         array.splice(pos, 1);
         array.splice(newPos, 0, tem);

         let newPath = path.slice();
         newPath[newPath.length - 1] = newPos;

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

      delete: function (path) {
         let {parent, key} = $.path2ParentnKey(path);

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

      addObjectEntry: function (parentPath, pos, key, valueClosure) {
         let value;

         try {
            value = valueClosure.call(null);
         }
         catch (e) {
            $.sendFailure(`Failed to evaluate a new value:\n ${e.stack}`)
            return;
         }

         // TODO: fix this ugliness
         let {parent, key: pkey} = $.path2ParentnKey(parentPath);
         parent = parent[pkey];

         if (Array.isArray(parent)) {
            parent.splice(pos, 0, value);

            let newPath = parentPath.slice();
            newPath.push(pos);

            $.sendSuccess(null, [{
               type: 'insert',
               path: newPath,
               key: null,
               value: $.prepareForSerialization(value)
            }]);
         }
         else {
            $.insertProp(parent, key, value, pos);   
            
            let newPath = parentPath.slice();
            newPath.push(pos);
            $.sendSuccess(null, [{
               type: 'insert',
               path: newPath,
               key: key,
               value: $.prepareForSerialization(value)
            }]);
         }
      },

      probe2: {
         what: "is",
         your: "name?"
      },

      probe: {
         firstName: "Iohann",
         reHero: /hero/,
         invalid: function (val) {
            return Array.isArray(val) && val[0] > 0;
         },
         lastName: "Black",
         xyz: [
            function () {
               console.log(/[a-z({\]((ab]/);
            },
            [
               function () { return 24; },
               [
                  "b",
                  {
                     some: 10,
                     woo: 20
                  },
                  "sake"
               ]
            ],
            "New Value"
         ],
         funcs: {
            js: function () {
               return 'js';
            },
            livejs: function () {
               return 'livejs';
            },
            python: function () {
               return 'Python3';
            }
         }
      }
   };

   return $;
})();


window.root.initOnLoad();
