if __name__ == '__main__':
    from live.sublime import *

    g_el.run_in_new_thread()
    start_server()
    g_el.join_coroutine('server')
