using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AiProfile
{
    /// <summary>
    /// AiProfileAgent - 跨项目通用的轻量嵌入式 Unity 性能监控与自动化控制 Agent
    /// 
    /// 【接入指南 (3分钟完成)】：
    /// 1. 将本脚本放入任意 Unity 项目的 Assets 目录；
    /// 2. 在游戏的第一个启动场景挂载本组件到一个常驻 GameObject 上（或调用 DontDestroyOnLoad）；
    /// 3. 在项目初始化代码中，绑定您项目自有的画质切换接口：
    /// 
    ///    AiProfileAgent.OnSetQualityRequested = (tier) => {
    ///        // 示例：对接您项目的画质管理单例
    ///        GameSettingManager.Instance.SetQualityTier(tier);
    ///    };
    /// </summary>
    public class AiProfileAgent : MonoBehaviour
    {
        public const int Port = 8989;

        /// <summary>
        /// 项目业务回调：当收到切画质指令时触发 (参数为 "Low", "Medium", "High", "Ultra" 或项目自定义名称)
        /// </summary>
        public static Action<string> OnSetQualityRequested;

        /// <summary>
        /// 项目业务回调：查询自定义状态 (可选，默认为当前场景名与实时FPS)
        /// </summary>
        public static Func<string> OnCustomStatusQuery;

        private TcpListener _listener;
        private Thread _listenThread;
        private volatile bool _isRunning = false;

        private float _fpsAccumulator = 0f;
        private int _fpsFrames = 0;
        private float _currentFps = 60f;

        private void Awake()
        {
            DontDestroyOnLoad(gameObject);
            StartServer();
        }

        private void Update()
        {
            _fpsAccumulator += Time.unscaledDeltaTime;
            _fpsFrames++;
            if (_fpsAccumulator >= 0.5f)
            {
                _currentFps = _fpsFrames / _fpsAccumulator;
                _fpsAccumulator = 0f;
                _fpsFrames = 0;
            }
        }

        private void OnDestroy()
        {
            StopServer();
        }

        private void StartServer()
        {
            if (_isRunning) return;
            try
            {
                _listener = new TcpListener(IPAddress.Any, Port);
                _listener.Start();
                _isRunning = true;
                _listenThread = new Thread(ListenLoop) { IsBackground = true };
                _listenThread.Start();
                Debug.Log($"[AiProfileAgent] 已在端口 {Port} 启动自动化监听服务");
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[AiProfileAgent] 启动监听服务失败: {ex.Message}");
            }
        }

        private void StopServer()
        {
            _isRunning = false;
            try
            {
                _listener?.Stop();
                _listenThread?.Abort();
            }
            catch { }
        }

        private void ListenLoop()
        {
            while (_isRunning)
            {
                try
                {
                    TcpClient client = _listener.AcceptTcpClient();
                    ThreadPool.QueueUserWorkItem(HandleClient, client);
                }
                catch (SocketException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[AiProfileAgent] 连接异常: {ex.Message}");
                }
            }
        }

        private void HandleClient(object obj)
        {
            using (TcpClient client = (TcpClient)obj)
            using (NetworkStream stream = client.GetStream())
            using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
            using (StreamWriter writer = new StreamWriter(stream, Encoding.UTF8) { AutoFlush = true })
            {
                string line = reader.ReadLine();
                if (string.IsNullOrEmpty(line)) return;

                string cmd = line.Trim();
                string response = ProcessCommand(cmd);
                writer.WriteLine(response);
            }
        }

        private string ProcessCommand(string cmd)
        {
            if (cmd.StartsWith("SET_QUALITY", StringComparison.OrdinalIgnoreCase))
            {
                string tier = cmd.Substring("SET_QUALITY".Length).Trim();
                Loom.QueueOnMainThread(() =>
                {
                    OnSetQualityRequested?.Invoke(tier);
                });
                return $"OK: SET_QUALITY={tier}";
            }
            else if (cmd.Equals("STATUS", StringComparison.OrdinalIgnoreCase))
            {
                string sceneName = SceneManager.GetActiveScene().name;
                string custom = OnCustomStatusQuery != null ? OnCustomStatusQuery() : "";
                return $"status=ready;scene={sceneName};fps={_currentFps:F1};timescale={Time.timeScale:F1};{custom}";
            }
            else if (cmd.Equals("FREEZE", StringComparison.OrdinalIgnoreCase))
            {
                Loom.QueueOnMainThread(() => Time.timeScale = 0f);
                return "OK: FREEZE";
            }
            else if (cmd.Equals("UNFREEZE", StringComparison.OrdinalIgnoreCase))
            {
                Loom.QueueOnMainThread(() => Time.timeScale = 1f);
                return "OK: UNFREEZE";
            }

            return $"UNKNOWN_CMD: {cmd}";
        }
    }

    internal class Loom
    {
        private static readonly System.Collections.Generic.Queue<Action> _actions = new System.Collections.Generic.Queue<Action>();

        public static void QueueOnMainThread(Action action)
        {
            lock (_actions)
            {
                _actions.Enqueue(action);
            }
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void Initialize()
        {
            GameObject g = new GameObject("AiProfile_Loom");
            UnityEngine.Object.DontDestroyOnLoad(g);
            g.AddComponent<LoomComponent>();
        }

        private class LoomComponent : MonoBehaviour
        {
            private void Update()
            {
                lock (_actions)
                {
                    while (_actions.Count > 0)
                    {
                        try { _actions.Dequeue()?.Invoke(); } catch (Exception e) { Debug.LogException(e); }
                    }
                }
            }
        }
    }
}

