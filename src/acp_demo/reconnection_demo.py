#!/usr/bin/env python3
"""
ACP 断连检测与重连机制 Demo

演示：
1. Client 如何检测 Agent 断连
2. 自动重连机制
3. Session 恢复
"""

import subprocess
import json
import time
import sys
import select


class ResilientACPClient:
    """支持断连检测和自动重连的 ACP Client"""
    
    def __init__(self, agent_module):
        self.agent_module = agent_module
        self.proc = None
        self.msg_id = 0
        self.connected = False
        self.session_id = None
        self.reconnect_count = 0
        self.max_reconnects = 3
        self.last_updates = []
    
    def log(self, msg):
        print(f"[Client] {msg}")
    
    # ----------------------------------------------------------
    #  连接管理
    # ----------------------------------------------------------
    
    def connect(self):
        """启动 Agent 进程"""
        self.log("启动 Agent 进程...")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", self.agent_module],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        time.sleep(0.5)
        
        # 检查是否启动成功
        if self.proc.poll() is not None:
            self.log(f"Agent 启动失败 (返回码: {self.proc.returncode})")
            self.connected = False
            return False
        
        self.connected = True
        self.log(f"Agent 已连接 (PID: {self.proc.pid})")
        return True
    
    def disconnect(self):
        """断开连接"""
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except:
                try:
                    self.proc.kill()
                except:
                    pass
            self.proc = None
        self.connected = False
        self.log("已断开连接")
    
    def is_alive(self):
        """检测 Agent 是否还活着"""
        if not self.proc:
            return False
        
        poll_result = self.proc.poll()
        if poll_result is not None:
            self.log(f"Agent 进程已退出 (返回码: {poll_result})")
            self.connected = False
            return False
        
        return True
    
    # ----------------------------------------------------------
    #  消息收发（带断连检测）
    # ----------------------------------------------------------
    
    def send(self, method, params, timeout=5):
        """发送请求，自动检测断连"""
        self.last_updates = []
        if not self.is_alive():
            self.log("Agent 不在线，无法发送")
            return None
        
        self.msg_id += 1
        request = {"jsonrpc": "2.0", "id": self.msg_id, "method": method, "params": params}
        
        # 写入 stdin（检测 BrokenPipe）
        try:
            self.proc.stdin.write(json.dumps(request) + "\n")
            self.proc.stdin.flush()
        except BrokenPipeError:
            self.log("写入失败: 管道已断开 (BrokenPipe)")
            self.connected = False
            return None
        except OSError as e:
            self.log(f"写入失败: {e}")
            self.connected = False
            return None
        
        # 读取响应（带超时检测）
        try:
            readable, _, _ = select.select([self.proc.stdout], [], [], timeout)
            
            if not readable:
                self.log(f"读取超时 ({timeout}s)")
                if not self.is_alive():
                    return None
                return {"error": "timeout"}
            
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    self.log("读取到 EOF: Agent 已断开")
                    self.connected = False
                    return None

                message = json.loads(line)
                if "method" in message:
                    self.last_updates.append(message)
                    continue
                if message.get("id") == self.msg_id:
                    return message
            
        except json.JSONDecodeError as e:
            self.log(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            self.log(f"读取异常: {e}")
            self.connected = False
            return None
    
    # ----------------------------------------------------------
    #  重连机制
    # ----------------------------------------------------------
    
    def reconnect(self):
        """重连 Agent"""
        self.reconnect_count += 1
        
        if self.reconnect_count > self.max_reconnects:
            self.log(f"重连次数超过上限 ({self.max_reconnects})，放弃重连")
            return False
        
        self.log(f"尝试重连 ({self.reconnect_count}/{self.max_reconnects})...")
        
        # 清理旧连接
        self.disconnect()
        
        # 等待一下再重连
        time.sleep(1)
        
        # 建立新连接
        if not self.connect():
            return False
        
        # 重新初始化
        resp = self.send("initialize", {
            "protocolVersion": 1,
            "clientInfo": {"name": "resilient-client"}
        })
        if not resp or "error" in resp:
            self.log("初始化失败")
            return False
        
        self.log("重连成功")
        return True
    
    def send_with_retry(self, method, params, timeout=5):
        """发送请求，失败自动重连重试"""
        for attempt in range(2):
            resp = self.send(method, params, timeout)
            
            if resp is not None:
                return resp
            
            # 断连了，尝试重连
            if not self.connected:
                if self.reconnect():
                    # 重连后恢复 Session
                    if self.session_id:
                        self.log(f"恢复 Session: {self.session_id}")
                        self.send("session/resume", {"sessionId": self.session_id})
                    continue
                else:
                    return None
            
            return resp
        
        return None
    
    # ----------------------------------------------------------
    #  高级操作
    # ----------------------------------------------------------
    
    def initialize(self):
        return self.send_with_retry("initialize", {
            "protocolVersion": 1,
            "clientInfo": {"name": "resilient-client", "version": "1.0"}
        })
    
    def new_session(self, cwd="/tmp"):
        resp = self.send_with_retry("session/new", {"cwd": cwd})
        if resp and "result" in resp:
            self.session_id = resp["result"].get("sessionId")
            self.log(f"Session: {self.session_id}")
        return resp
    
    def prompt(self, text):
        if not self.session_id:
            self.log("没有活跃 Session")
            return None
        return self.send_with_retry("session/prompt", {
            "sessionId": self.session_id,
            "prompt": [{"type": "text", "text": text}]
        })


# ============================================================
#  演示
# ============================================================

def main():
    print("=" * 60)
    print("  ACP 断连检测与重连机制 Demo")
    print("=" * 60)
    
    agent_module = "acp_demo.crash_agent"
    
    client = ResilientACPClient(agent_module)
    
    # 连接
    print("\n[1] 初始连接...")
    if not client.connect():
        print("连接失败，退出")
        return
    
    # 初始化
    print("\n[2] 初始化...")
    client.initialize()
    
    # 创建 Session
    print("\n[3] 创建 Session...")
    client.new_session()
    
    # 发送多个请求（有些会触发崩溃）
    print("\n[4] 发送请求（Agent 有 20% 概率崩溃，自动重连）...")
    success = 0
    fail = 0
    
    for i in range(8):
        print(f"\n--- 请求 {i+1} ---")
        resp = client.prompt(f"问题 {i+1}")
        for update in client.last_updates:
            text = update.get("params", {}).get("update", {}).get("content", {}).get("text")
            if text:
                print(f"  update: {text}")
        
        if resp and resp.get("result", {}).get("stopReason") == "end_turn":
            print(f"  结果: 成功")
            success += 1
        elif resp and "error" in resp:
            print(f"  结果: 错误 - {resp['error']}")
            fail += 1
        else:
            print(f"  结果: 失败（已尝试重连）")
            fail += 1
    
    # 清理
    client.disconnect()
    
    # 总结
    print("\n" + "=" * 60)
    print("  结果统计")
    print("=" * 60)
    print(f"""
  成功: {success}/8
  失败: {fail}/8
  重连次数: {client.reconnect_count}
""")


if __name__ == "__main__":
    main()
