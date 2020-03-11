(function () {
   'use strict';

   const 
      port = LIVEJS_PORT,
      projectModuleName = LIVEJS_PROJECT_MODULE_NAME,
      projectPath = LIVEJS_PROJECT_PATH;

   function urlOf(moduleName) {
      return `http://localhost:${port}/bootload/${moduleName}.js`;
   }

   function sourceOf(moduleName) {
      return fetch(urlOf(moduleName)).then(r => r.text());
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
         project = window.eval(await sourceOf(projectModuleName)),
         sources = await allKeyed(
            project['modules'].map(m => [m['id'], sourceOf(m['name'])])
         ),
         bootstrapper$ = window.eval(sources[project['bootstrapper']]);

      bootstrapper$['bootload'].call(null, {projectPath, port, project, sources});
   })()
      .catch(onError);
})();
