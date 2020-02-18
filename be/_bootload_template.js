(function () {
   const 
      port = LIVEJS_PORT,
      mainModuleName = LIVEJS_MAIN_MODULE_NAME,
      otherModuleNames = LIVEJS_OTHER_MODULE_NAMES,
      projectPath = LIVEJS_PROJECT_PATH,
      url = `http://localhost:${port}/bootload/`;

   let
      promiseMain = fetch(url + mainModuleName).then(r => r.text()),
      promises = otherModuleNames.map(name => fetch(url + name).then(r => r.text()));

   promises.unshift(promiseMain);

   Promise.all(promises).then(srcModules => {
      let srcMain = srcModules.shift();
      let otherModules = [];

      for (let i = 0; i < otherModuleNames.length; i += 1) {
         otherModules.push({
            name: otherModuleNames[i],
            src: srcModules[i]
         });
      }
      
      let main = window.eval(srcMain);

      main['bootload'].call(null, {
         otherModules,
         projectPath,
         port
      });
   })
   .catch(function (e) {
      console.error("LiveJS: bootloading process failed:", e);
   });

})();
