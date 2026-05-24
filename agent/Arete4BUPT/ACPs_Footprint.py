import requests

class ACPs_Footprint:
    @staticmethod
    def notify(url, AgentName_src, src_AIC, AgentName_dist, dest_AIC):
        """
        向足迹展示后台发送任务流转通知 (包含AIC标识)
        :param url: ACPs足迹后台服务的 REST-API 端点 (必填)
        :param AgentName_src: 发起任务的智能体名称 (必填)
        :param src_AIC: 发起任务的智能体唯一标识码 (必填)
        :param AgentName_dist: 接收任务的智能体名称 (必填)
        :param dest_AIC: 接收任务的智能体唯一标识码 (必填)
        """
        try:
            # 将源智能体和目标智能体的名称与AIC打包成JSON数据
            data = {
                "AgentName_src": AgentName_src,
                "src_AIC": src_AIC,
                "AgentName_dist": AgentName_dist,
                "dest_AIC": dest_AIC
            }
            # 向后端大屏发送POST请求 (设置了较短的超时时间，防止阻塞智能体本身的运行)
            requests.post(url, json=data, timeout=3)
            print(f"[SDK 通知成功] {AgentName_src}[{src_AIC}] ➔ {AgentName_dist}[{dest_AIC}]")
        except Exception as e:
            print(f"[SDK 通知失败] 请检查大屏地址是否正确或网络是否连通。错误信息: {e}")