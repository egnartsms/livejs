window.root = (function () {
   let $ = {};

   $.nontrackedKeys = [
      'socket',
   ];

   $.socket = null;

   $.initOnLoad = function () {
      $.resetSocket();
   };

   $.onSocketOpen = function () {
      console.log("Connected to LiveJS FE");
   };

   $.onSocketClose = function (evt) {
      $.resetSocket();
   };

   $.resetSocket = function () {
      $.socket = new WebSocket('ws://localhost:8001/wsconnect');
      $.socket.onmessage = $.onSocketMessage;
      $.socket.onopen = $.onSocketOpen;
      $.socket.onclose = $.onSocketClose;
   };

   $.onSocketMessage = function (e) {
      let func;
      
      try {
         func = new Function('$', e.data);
      }
      catch (e) {
         $.sendFailure(`Failed to compile JS code:\n ${e}`);
      }

      try { 
         func.call(null, $);
      }
      catch (e) {
         $.sendFailure(`Unhandled exception:\n ${e.stack}`);
      }
   };

   $.prepareForSerialization = function prepare(obj) {
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

      if (Object.getPrototypeOf(obj) !== Object.prototype) {
         throw new Error(`Cannot serialize objects with non-standard prototype`);
      }

      return Object.fromEntries(
         Object.entries(obj).map(([k, v]) => [k, prepare(v)])
      );
   };

   $.send = function (msg) {
      $.socket.send(JSON.stringify(msg));
   };

   $.sendFailure = function (message) {
      $.send({
         success: false,
         message: message
      });
   };

   $.sendSuccess = function (response, actions=null) {
      $.send({
         success: true,
         response: response,
         actions: actions || []
      });
   };

   $.sendActions = function (actions) {
      if (!Array.isArray(actions)) {
         actions = [actions];
      }
      $.sendSuccess(null, actions);
   };
   
   $.sendAllEntries = function () {
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
   };
   
   $.edit = function (path, newValueClosure) {
      let newValue;

      try {
         newValue = newValueClosure.call(null);
      }
      catch (e) {
         $.sendFailure(`Failed to evaluate a new value:\n ${e.stack}`)
         return;
      }

      let {parent, key} = $.path2ParentnKey(path);
      console.log(parent, key);
      parent[key] = newValue;

      $.sendActions({
         type: 'edit',
         path: path,
         newValue: $.prepareForSerialization(newValue)
      });
   };

   $.path2ParentnKey = function (path) {
      let parent = $, key, i = 0;

      // invariant: key

      for (;;) {
         let n = path[i], child;

         if (Array.isArray(parent)) {
            [key, child] = [String(n), parent[n]];
         }
         else {
            [key, child] = Object.entries(parent)[n];
         }

         i += 1;
         if (i === path.length) {
            break;
         }
         else {
            parent = child;   
         }
      }

      return {parent, key};
   };

   $.testObj = {
      first_name: "Iohann",
      last_name: [120, function () {
            console.log(/[a-z({\]((ab]/);
         }],
      functions: {
         play: [
            "on",
            [
               "Ukraine",
               "Gonduras",
            ],
            function (x, y) {
               return x + y;
            },
         ],
         stop: function () {
            console.log("Bach plays no more")
         }
      }
   };

   return $;
})();


window.root.initOnLoad();
