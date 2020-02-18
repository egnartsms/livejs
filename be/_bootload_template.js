(function () {
   const 
      port = LIVEJS_PORT,
      mainModule = LIVEJS_MAIN_MODULE,
      otherModules = LIVEJS_OTHER_MODULES,
      livejsUrl = `http://localhost:${port}/bootload/`;

   let
      promiseMain = fetch(livejsUrl + mainModule).then(r => r.text()),
      promises = otherModules.map(module => fetch(livejsUrl + module).then(r => r.text()));

   promises.unshift(promiseMain);

   Promise.all(promises).then(srcModules => {
      let srcMain = srcModules.shift();
      let modulesToBootload = [];

      for (let i = 0; i < otherModules.length; i += 1) {
         modulesToBootload.push({
            name: otherModules[i],
            src: srcModules[i]
         });
      }
      
      let main = window.eval(srcMain);
      main['bootload'].call(null, modulesToBootload);
   })
   .catch(function (e) {
      console.log("LiveJS: bootloading process failed:", e);
   });

})();
