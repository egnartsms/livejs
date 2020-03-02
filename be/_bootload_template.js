(function () {
   const 
      port = LIVEJS_PORT,
      projectModuleName = LIVEJS_PROJECT_MODULE_NAME,
      projectPath = LIVEJS_PROJECT_PATH;

   function urlOf(moduleName) {
      return `http://localhost:LIVEJS_PORT/bootload/${moduleName}.js`;
   }

   function sourceOf(moduleName) {
      return fetch(urlOf(moduleName)).then(r => r.text());
   }

   function onError(e) {
      console.error("LiveJS: bootloading process failed:", e);
   }

   (async function () {
      let
         project = window.eval(await sourceOf(projectModuleName)),
         projectModules = project['modules'],
         sources = await Promise.all(projectModules.map(({name}) => sourceOf(name))),
         idxBootstrapper = projectModules.findIndex(
            ({id}) => id === project['bootstrapper']
         ),
         [moduleBootstrapper] = projectModules.splice(idxBootstrapper, 1),
         [sourceBootstrapper] = sources.splice(idxBootstrapper, 1);

      for (let i = 0; i < projectModules.length; i += 1) {
         projectModules[i]['source'] = sources[i];
      }

      let bootstrapper$ = window.eval(sourceBootstrapper);

      bootstrapper$['bootload'].call(null, {
         myself: moduleBootstrapper,
         modules: projectModules,
         projectId: project['projectId'],
         projectPath: projectPath,
         port: port
      });
   })()
      .catch(onError);
})();
