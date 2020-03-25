(function () {
   'use strict';

   const 
      PORT = {{PORT}},
      PROJECT_FILE_NAME = {{PROJECT_FILE_NAME}},
      PROJECT_PATH = {{PROJECT_PATH}};

   function fileUrl(filename) {
      return `http://localhost:${PORT}/bootload/${filename}`;
   }

   function moduleUrl(moduleName) {
      return fileUrl(moduleName + '.js');
   }

   function sourceOf(moduleName) {
      return fetch(moduleUrl(moduleName)).then(r => r.text());
   }

   function projectFileSource() {
      return fetch(fileUrl(PROJECT_FILE_NAME)).then(r => r.text());
   }

   function onError(e) {
      console.error("LiveJS: bootloading process failed:", e);
   }

   async function allKeyed(entries) {
      let promises = entries.map(([, promise]) => promise);
      let results = await Promise.all(promises);
      
      let resultObj = {};
      for (let i = 0; i < entries.length; i += 1) {
         resultObj[entries[i][0]] = results[i];
      }
      return resultObj;
   }

   (async function () {
      let
         project = JSON.parse(await projectFileSource()),
         sources = await allKeyed(
            project['modules'].map(m => [m['id'], sourceOf(m['name'])])
         ),
         bootstrapper$ = window.eval(sources[project['bootstrapper']]);

      bootstrapper$['bootload'].call(null, {
         projectPath: PROJECT_PATH, 
         port: PORT,
         project,
         sources
      });
   })()
      .catch(onError);
})();
