(function () {
   'use strict';

   let $ = {
      projects: null,
      modules: null,
      port: null,
      socket: null,

      bootload: function ({projectPath, port, project, sources}) {
         let 
            bootstrapper = project['modules'].find(
               m => m['id'] === project['bootstrapper']
            ),
            modules = $.loadModules(
               project['modules'].filter(m => m !== bootstrapper),
               sources,
               project['projectId']
            );

         // The bootstrapper needs to be added to this array manually
         modules.push(Object.assign({}, bootstrapper, {
            projectId: project['projectId'],
            value: $,
         }));

         $.projects = {
            [project['projectId']]: {
               id: project['projectId'],
               name: project['projectName'],
               path: projectPath,
               modules: $.byId(modules)
            }
         };
         $.modules = $.byId(modules);
      
         $.port = port;
         $.orderedKeysMap = new WeakMap;
         $.inspectionSpaces = {};
      
         $.resetSocket();
      
         // This is just to be able to access things in Chrome console
         window.live = $;
      },

      byId: function (things) {
         let res = {};
         for (let thing of things) {
            res[thing.id] = thing;
         }
         return res;
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
         let msg = JSON.parse(evt.data);

         try {
            $.opHandlers[msg['operation']].call(null, msg['args']);
         }
         catch (e) {
            $.opExc('generic', {
               message: e.stack
            });
         }
      },

      send: function (message) {
         $.socket.send(JSON.stringify(message));
      },

      opExc: function (error, info) {
         $.send({
            type: 'result',
            success: false,
            error: error,
            info: info
         });
      },

      opReturn: function (value=null) {
         $.send({
            type: 'result',
            success: true,
            value: value
         });
      },

      persist: function (descriptors) {
         $.send({
            type: 'persist',
            descriptors: descriptors
         });
      },

      persistInModule: function (module, descriptors) {
         if (!(descriptors instanceof Array)) {
            descriptors = [descriptors];
         }

         for (let desc of descriptors) {
            desc['projectId'] = module.projectId;
            desc['moduleId'] = module.id;
            desc['moduleName'] = module.name;
         }

         $.persist(descriptors);
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

      isArray: function (obj) {
         return Array.isArray(obj) && obj !== Array.prototype;
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

      moduleObject: function (mid) {
         return $.modules[mid].value;
      },

      inspectionSpaces: null,

      inspectionSpace: function (spaceId) {
         if (!(spaceId in $.inspectionSpaces)) {
            $.inspectionSpaces[spaceId] = {
               obj2id: new Map,
               id2obj: new Map,
               id2nrefs: new Map,
               // ID of an inspectee that should miss 1 addref operation
               idDontRef: null,
               nextId: 1
            };
         }
      
         return $.inspectionSpaces[spaceId];
      },

      isObjectOrFunction: function (object) {
         return (
            (typeof object === 'object' && object !== null) ||
            (typeof object === 'function')
         );
      },

      refInspectee: function (space, object) {
         if (!$.isObjectOrFunction(object)) {
            throw new Error(`Invalid inspectee: ${object}`);
         }
      
         if (!space.obj2id.has(object)) {
            let id = space.nextId++;
            space.obj2id.set(object, id);
            space.id2obj.set(id, object);
            space.id2nrefs.set(id, 1);
            return id;
         }
         else {
            let id = space.obj2id.get(object);
      
            if (id === space.idDontRef) {
               space.idDontRef = null;
               return id;
            }
      
            let nrefs = space.id2nrefs.get(id);
            space.id2nrefs.set(id, nrefs + 1);
            return id;
         }
      },

      releaseInspecteeId: function (space, id) {
         let nrefs = space.id2nrefs.get(id);

         if (nrefs === undefined) {
            throw new Error(`Unknown inspectee ID: ${id}`);
         }

         if (nrefs === 1) {
            let object = space.id2obj.get(id);
            space.id2obj.delete(id);
            space.obj2id.delete(object);
            space.id2nrefs.delete(id);
         }
         else {
            space.id2nrefs.set(id, nrefs - 1);
         }
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
      
         return $.inspectObject(space, obj, deeply);
      },

      inspectObject: function (space, object, deeply) {
         if ($.isArray(object)) {
            let res = {
               type: 'array',
               id: $.refInspectee(space, object)
            };
      
            if (deeply) {
               res['value'] = Array.from(object, x => $.inspect(space, x, false));
            }
      
            return res;
         }
      
         let objectId = $.refInspectee(space, object);
         let res = {
            type: 'object',
            id: objectId
         };
      
         if (!deeply) {
            return res;
         }
      
         let attrs = {
            __proto: $.inspect(space, Object.getPrototypeOf(object), false)
         };
         let nonvalues = {};
      
         for (let [prop, desc] of Object.entries(Object.getOwnPropertyDescriptors(object))) {
            if ($.hasOwnProperty(desc, 'value')) {
               attrs[prop] = $.inspect(space, desc.value, false);
            }
            else {
               attrs[prop] = {
                  type: 'unrevealed',
                  parentId: objectId,
                  prop: prop
               };
               nonvalues[prop] = desc;
            }
         }
      
         for (let [prop, desc] of Object.entries(nonvalues)) {
            if (desc.get) {
               attrs['get ' + prop] = $.inspectFunc(space, desc.get);
            }
            if (desc.set) {
               attrs['set ' + prop] = $.inspectFunc(space, desc.set);
            }
         }
      
         res['value'] = attrs;
      
         return res;
      },

      inspectFunc: function (space, func) {
         return {
            type: 'function',
            id: $.refInspectee(space, func),
            value: func.toString()
         };
      },

      isKeyUntracked: function (module, key) {
         return module.untracked.includes(key);
      },

      loadModule: function (module, source, projectId) {
         let value = window.eval(source);
   
         if (value['init']) {
            value['init'].call(null);
         }
   
         return Object.assign({}, module, {projectId, value});
      },

      loadModules: function (modules, sources, projectId) {
         // modules: [<same as in project file>]
         let result = [];

         for (let module of modules) {
            let source = sources[module['id']];
            if (!source) {
               throw new Error(`Not provided source code for module ${module['name']}`);
            }

            result.push($.loadModule(module, source, projectId));
         }

         return result;
      },

      browseModuleMember: function (module, key, value) {
         if ($.isKeyUntracked(module, key)) {
            return {
               isTracked: false,
               value: $.inspect($.inspectionSpace(module.id), value, false)
            };
         }
         else {
            return {
               isTracked: true,
               value: $.serialize(value)
            };
         }
      },
      opHandlers: {
         getProjects: function () {
            $.opReturn(
                  Object.values($.projects).map(proj => ({
                     id: proj.id,
                     name: proj.name,
                     path: proj.path
                  }))
            );
         },
         getProjectModules: function ({projectId}) {
            let project = $.projects[projectId];

            $.opReturn(Object.values(project.modules).map(module => ({
               id: module.id,
               name: module.name
            })));
         },
         getProjectArbitraryModule: function ({projectId}) {
            let project = $.projects[projectId];
            let module = Object.values(project.modules)[0];

            $.opReturn({
               id: module.id,
               name: module.name
            });
         },
         loadProject: function ({projectPath, project, sources}) {
            if (project['projectId'] in $.projects) {
               throw new Error(`Project is already loaded`);
            }
            if (project['modules'].some(m => m['id'] in $.modules)) {
               throw new Error(`Duplicate module id`)
            }

            let modules = $.loadModules(
               project['modules'], sources, project['projectId']
            );
         
            $.projects[project['projectId']] = {
               id: project['projectId'],
               name: project['projectName'],
               path: projectPath,
               modules: $.byId(modules)
            };
         
            Object.assign($.modules, $.byId(modules));
         
            $.opReturn();
         },
         loadModule: function ({projectId, moduleId, name, source, untracked}) {
            let project = $.projects[projectId];

            if (!project) {
               throw new Error(`Project with given ID is not loaded`);
            }

            if (moduleId in $.modules) {
               throw new Error(`Module ID duplicated`);
            }

            if (Object.values(project.modules).find(m => m.name === name)) {
               throw new Error(`Cannot add module "${name}": duplicate name`);
            }

            let module = $.loadModule(
               {
                  id: moduleId,
                  name,
                  untracked
               },
               source,
               projectId
            );
            
            $.modules[module.id] = module;
            project.modules[module.id] = module;

            $.opReturn();
         },
         getKeyAt: function ({mid, path}) {
            $.opReturn($.keyAt($.moduleObject(mid), path));
         },
         getValueAt: function ({mid, path}) {
            $.opReturn(
               $.serialize($.valueAt($.moduleObject(mid), path))
            );
         },
         browseModuleMember: function ({mid, key}) {
            let module = $.modules[mid];
         
            return $.opReturn($.browseModuleMember(module, key, module.value[key]));
         },
         browseModule: function ({mid}) {
            let
               result = [],
               module = $.modules[mid];
         
            for (let [key, value] of $.entries(module.value)) {
               result.push([key, $.browseModuleMember(module, key, value)]);
            }
         
            $.opReturn(result);
         },
         getModuleEntries: function ({mid}) {
            let
               result = [],
               module = $.modules[mid],
               space = $.inspectionSpace(mid);
         
            for (let [key, value] of $.entries(module.value)) {
               let data;
         
               if ($.isKeyUntracked(module, key)) {
                  data = {
                     isTracked: false,
                     value: $.inspect(space, value, false)
                  };
               }
               else {
                  data = {
                     isTracked: true,
                     value: $.serialize(value)
                  };
               }
         
               result.push([key, data]);
            }
         
            $.opReturn(result);
         },
         replace: function ({mid, path, codeNewValue}) {
            let 
               module = $.modules[mid],
               {parent, key} = $.parentKeyAt(module.value, path),
               newValue = $.evalExpr(module.value, codeNewValue);
         
            parent[key] = newValue;
         
            $.persistInModule(module, {
               operation: 'replace',
               path,
               newValue: $.serialize(newValue)
            });
            $.opReturn();
         },
         renameKey: function ({mid, path, newName}) {
            let 
               module = $.modules[mid],
               {parent, key} = $.parentKeyAt(module.value, path);
         
            $.checkObject(parent);
         
            if ($.hasOwnProperty(parent, newName)) {
               $.opExc('duplicate_key', {
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
         
            $.persistInModule(module, {
               operation: 'rename_key',
               path,
               newName
            });
            $.opReturn();
         },
         addArrayEntry: function ({mid, parentPath, pos, codeValue}) {
            let
               module = $.modules[mid],
               parent = $.valueAt(module.value, parentPath),
               value = $.evalExpr(module.value, codeValue);
         
            $.checkArray(parent);
         
            parent.splice(pos, 0, value);
         
            $.persistInModule(module, {
               operation: 'insert',
               path: parentPath.concat(pos),
               key: null,
               value: $.serialize(value)
            });
            $.opReturn();
         },
         addObjectEntry: function ({mid, parentPath, pos, key, codeValue}) {
            let 
               module = $.modules[mid],
               parent = $.valueAt(module.value, parentPath),
               value = $.evalExpr(module.value, codeValue);
         
            $.checkObject(parent);
            if ($.hasOwnProperty(parent, key)) {
               throw new Error(`Cannot insert property ${key}: it already exists`);
            }
         
            $.insertProp(parent, key, value, pos);   
         
            $.persistInModule(module, {
               operation: 'insert',
               path: parentPath.concat(pos),
               key: key,
               value: $.serialize(value)
            });
            $.opReturn();
         },
         move: function ({mid, path, fwd}) {
            let 
               module = $.modules[mid],
               {parent, key} = $.parentKeyAt(module.value, path),
               value = parent[key],
               newPos;
         
            if (parent instanceof Array) {
               newPos = $.moveArrayItem(parent, key, fwd);
            }
            else {
               let props = $.ensureOrdkeys(parent);
               newPos = $.moveArrayItem(props, props.indexOf(key), fwd);
            }
         
            let newPath = path.slice(0, -1);
            newPath.push(newPos);
         
            $.persistInModule(module, [
               {
                  operation: 'delete',
                  path: path
               }, 
               {
                  operation: 'insert',
                  path: newPath,
                  key: parent instanceof Array ? null : key,
                  value: $.isKeyUntracked(module, key) ?
                     $.serialize('new Object()') : $.serialize(value)
               }
            ]);
            $.opReturn(newPath);
         },
         deleteEntry: function ({mid, path}) {
            let 
               module = $.modules[mid],
               {parent, key} = $.parentKeyAt(module.value, path);
         
            if (parent instanceof Array) {
               parent.splice(path[path.length - 1], 1);
            }
            else {
               $.deleteProp(parent, key);
            }
         
            $.persistInModule(module, {
               operation: 'delete',
               path: path
            });
            $.opReturn();
         },
         replEval: function ({mid, spaceId, code}) {
            let obj = $.evalExpr($.modules[mid].value, code);
            $.opReturn($.inspect($.inspectionSpace(spaceId), obj, true));
         },
         reinspectObject: function ({spaceId, inspecteeId}) {
            let space = $.inspectionSpace(spaceId);
            let object = space.id2obj.get(inspecteeId);
            if (!object) {
               throw new Error(`Unknown inspectee id: ${inspecteeId}`);
            }

            space.idDontRef = inspecteeId;
            $.opReturn($.inspect(space, object, true));
         },
         releaseInspecteeIds: function ({spaceId, inspecteeIds}) {
            let space = $.inspectionSpace(spaceId);
            for (let inspecteeId of inspecteeIds) {
               $.releaseInspecteeId(space, inspecteeId);
            }
            $.opReturn();
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
               $.opExc('getter_threw', {
                  excClassName: e.constructor.name,
                  excMessage: e.message,
                  message: `Getter threw an exception`
               });
               return;
            }
         
            $.opReturn($.inspect(space, result, true));
         },
         releaseInspectionSpace: function ({spaceId}) {
            let space = $.inspectionSpaces[spaceId];
            if (!space) {
               $.opReturn(false);
               return;
            }
         
            space.id2obj.clear();
            space.obj2id.clear();
            space.id2nrefs.clear();
            delete $.inspectionSpaces[spaceId];
         
            $.opReturn(true);
         }
      }
   };

   return $;
})();
