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
      $.sendMsg("LiveJS browser established connection");
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
         $.sendMsg(`Bad JS code:\n ${e}`);
      }

      try { 
         func.call(null, $);
      }
      catch (e) {
         $.sendMsg(`Exception:\n ${e}`);
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

   $.sendMsg = function (msg) {
      $.send({type: 'msg', msg});
   };

   $.sendResp = function (resp) {
      $.send({type: 'resp', resp});
   };
   
   $.sendAllEntries = function () {
      let result = [];
      for (let [key, value] of Object.entries($)) {
         if ($.nontrackedKeys.includes(key)) {
            continue;
         }

         result.push([key, $.prepareForSerialization(value)]);
      }

      $.sendResp(result);
   };
   
   $.testObj = {
      first_name: "Iohann",
      last_name: "Bach",
      functions: {
         play: function () {
            console.log("Bach plays")
         },
         stop: function () {
            console.log("Bach plays no more")
         }
      }
   };

   return $;
})();


window.root.initOnLoad();
