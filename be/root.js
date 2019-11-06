window.root = {
   nontrackedKeys: [
      'socket',
      'jsIndent',
      'jsIndentStr',
      'pieces',
   ],
   
   socket: null,

   jsIndent: 0,
   
   jsIndentStr: '',

   initOnLoad: function () {
      this.resetSocket();
   },

   initOnConnect: function (options) {
      this.jsIndent = options.jsIndent;
      this.jsIndentStr = ' '.repeat(this.jsIndent);
   },

   onSocketOpen: function (msg) {
      this.send({
         type: 'msg',
         msg: "Live system is ready!"
      });
   },

   resetSocket: function () {
      if (this.socket !== null) {
         throw new Error("Re-creating socket not implemented yet");
      }
      
      this.socket = new WebSocket('ws://localhost:8001/wsconnect');
      this.socket.onmessage = this.onSocketMessage.bind(this);
      this.socket.onopen = this.onSocketOpen.bind(this);
   },

   onSocketMessage: function (e) {
      let func;
      
      console.log(`Got: ${e.data}`);

      try {
         func = new Function(e.data);
      }
      catch (e) {
         this.send({
            type: 'msg',
            msg: `Bad JS code:\n ${e}`
         });
      }

      try { 
         func.call(this);
      }
      catch (e) {
         this.send({
            type: 'msg',
            msg: `Exception:\n ${e}`
         });
      }
   },

   pieces: [],
   
   sdump: function (obj, nesting=0) {
      if (typeof obj === 'function') {
         this.sdumpFunc(obj, nesting);
      }
      else if (Array.isArray(obj)) {
         this.sdumpArray(obj, nesting);
      }
      else if (typeof obj === 'object') {
         this.sdumpObject(obj, nesting)
      }
      else {
         this.pieces.push(JSON.stringify(obj, null, this.jsIndent));
      }
   },

   sdumpFunc: function (func, nesting) {
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
        
      this.pieces.push(lines[0]);
      for (let i = 1; i < lines.length; i += 1) {
         this.pieces.push(
            '\n',
            this.jsIndentStr.repeat(nesting),
            lines[i].slice(baseIndentation)
         );
      }
   },

   sdumpArray: function (array, nesting) {
      this.pieces.push('[\n');
      for (let elem of array) {
         this.pieces.push(this.jsIndentStr.repeat(nesting + 1));
         this.sdump(elem, nesting + 1);
         this.pieces.push(',\n');
      }
      this.pieces.push(
         this.jsIndentStr.repeat(nesting),
         ']'
      );
   },

   sdumpObject: function (obj, nesting) {
      if (obj === null) {
         this.pieces.push('null');
         return;
      }
      this.pieces.push('{');
      for (let key in obj) {
         this.pieces.push(
            '\n',
            this.jsIndentStr.repeat(nesting + 1),
            key,
            ': '
         );
         this.sdump(obj[key], nesting + 1);
         this.pieces.push(',');
      }

      this.pieces.push(
         '\n',
         this.jsIndentStr.repeat(nesting),
         '}'
      );
   },

   serialize: function (obj, nesting=0) {
      this.sdump(obj, nesting);
      let res = this.pieces.join('');
      this.pieces.length = 0;
      return res;
   },

   send: function (msg) {
      this.socket.send(JSON.stringify(msg));
   },

   sendResponse: function (response) {
      this.send({
         type: 'response',
         response
      });
   },
   
   sendAllEntries: function () {
      let result = [];
      for (let [key, value] of Object.entries(this)) {
         if (this.nontrackedKeys.includes(key)) {
            continue;
         }

         result.push([key, this.serialize(value, 0)]);
      }

      this.sendResponse(result);
   },
   
   saveKey: function (key) {
      this.send({
         type: 'save-key',
         key: key,
         value: this.serialize(this[key])
      });
   },

};


window.root.initOnLoad();
