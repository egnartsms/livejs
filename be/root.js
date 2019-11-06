window.root = (function () {
   let $ = {};

   $.nontrackedKeys = [
      'socket',
      'jsIndent',
      'jsIndentStr',
      'pieces',
   ];

   $.socket = null;

   $.jsIndent = 3;
   
   $.jsIndentStr = '   ';

   $.initOnLoad = function () {
      $.resetSocket();
   };

   $.onSocketOpen = function (msg) {
      $.send({
         type: 'msg',
         msg: "Live system is ready!"
      });
   };

   $.resetSocket = function () {
      if ($.socket !== null) {
         throw new Error("Re-creating socket not implemented yet");
      }
      
      $.socket = new WebSocket('ws://localhost:8001/wsconnect');
      $.socket.onmessage = $.onSocketMessage;
      $.socket.onopen = $.onSocketOpen;
   };

   $.onSocketMessage = function (e) {
      let func;
      
      try {
         func = new Function('$', e.data);
      }
      catch (e) {
         $.send({
            type: 'msg',
            msg: `Bad JS code:\n ${e}`
         });
      }

      try { 
         func.call(null, $);
      }
      catch (e) {
         $.send({
            type: 'msg',
            msg: `Exception:\n ${e}`
         });
      }
   };

   $.pieces = [];
   
   $.sdump = function (obj, nesting=0) {
      if (typeof obj === 'function') {
         $.sdumpFunc(obj, nesting);
      }
      else if (Array.isArray(obj)) {
         $.sdumpArray(obj, nesting);
      }
      else if (typeof obj === 'object') {
         $.sdumpObject(obj, nesting)
      }
      else {
         $.pieces.push(JSON.stringify(obj, null, $.jsIndent));
      }
   };

   $.sdumpFunc = function (func, nesting) {
      let str = Function.prototype.toString.call(func);
      let lines = str.split('\n');

      let indents = [];

      for (let i = 1; i < lines.length; i += 1) {
         let line = lines[i];
         // Any number of spaces followed by at least 1 non-whitespace.
         // All-whitespace lines (as well as empty ones) are not counted.
         let mo = /^\s*(?=\S)/.exec(line);
         if (mo !== null) {
            indents.push(mo[0].length);
         }
      }
      
      let baseIndentation = indents.length === 0 ? 0 :
          Math.min.apply(null, indents);

      // console.log("Base indentation for", func, "is", baseIndentation);
        
      $.pieces.push(lines[0]);
      for (let i = 1; i < lines.length; i += 1) {
         $.pieces.push(
            '\n',
            $.jsIndentStr.repeat(nesting),
            lines[i].slice(baseIndentation)
         );
      }
   };

   $.sdumpArray = function (array, nesting) {
      $.pieces.push('[\n');
      for (let elem of array) {
         $.pieces.push($.jsIndentStr.repeat(nesting + 1));
         $.sdump(elem, nesting + 1);
         $.pieces.push(',\n');
      }
      $.pieces.push(
         $.jsIndentStr.repeat(nesting),
         ']'
      );
   };

   $.sdumpObject = function (obj, nesting) {
      if (obj === null) {
         $.pieces.push('null');
         return;
      }
      $.pieces.push('{');
      for (let key in obj) {
         $.pieces.push(
            '\n',
            $.jsIndentStr.repeat(nesting + 1),
            key,
            ': '
         );
         $.sdump(obj[key], nesting + 1);
         $.pieces.push(',');
      }

      $.pieces.push(
         '\n',
         $.jsIndentStr.repeat(nesting),
         '}'
      );
   };

   $.serialize = function (obj, nesting=0) {
      $.sdump(obj, nesting);
      let res = $.pieces.join('');
      $.pieces.length = 0;
      return res;
   };

   $.send = function (msg) {
      $.socket.send(JSON.stringify(msg));
   };

   $.sendResponse = function (response) {
      $.send({
         type: 'response',
         response
      });
   };
   
   $.sendAllEntries = function () {
      let result = [];
      for (let [key, value] of Object.entries($)) {
         if ($.nontrackedKeys.includes(key)) {
            continue;
         }

         result.push([key, $.serialize(value, 0)]);
      }

      $.sendResponse(result);
   };
   
   $.saveKey = function (key) {
      $.send({
         type: 'save-key',
         key: key,
         value: $.serialize($[key])
      });
   };

   return $;
})();


window.root.initOnLoad();
