;; -*- lexical-binding: t; -*-

(defun lv-get-buffer-init (bufname init-fn)
  (let ((buf (get-buffer bufname)))
    (or buf
	(with-current-buffer
	    (get-buffer-create bufname)
	  (funcall init-fn)
	  (current-buffer)))))


(provide 'live-util)
